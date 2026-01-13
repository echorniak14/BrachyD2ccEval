from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from typing import List, Optional
import json
import pydicom
import io
from pydantic import BaseModel

# --- FIX: Define router BEFORE importing internal modules ---
# This prevents "AttributeError: has no attribute 'router'" during circular imports
router = APIRouter()
# ------------------------------------------------------------

# Services
from ..services.parser_service import ParserService
from ..services.dwell_time_service import generate_dwell_time_sheet
from ..services.optimization_service import OptimizationService
from ..services.report_generator import convert_html_to_pdf

# Core
from ..core import calculations, validators
from ..config import templates

# Dependencies
def get_parser_service():
    return ParserService()

def get_optimization_service():
    return OptimizationService()

class OptimizationGoalRequest(BaseModel):
    total_eqd2_constraint: float
    organ_name: str 
    number_of_fractions: int
    ebrt_dose: float = 0.0
    ebrt_fractions: int = 1
    previous_brachy_bed: float = 0.0
    alpha_beta_ratios: Optional[dict] = None

class PdfGenerationRequest(BaseModel):
    html_content: str

class BatchOptimizationGoalRequest(BaseModel):
    requests: List[OptimizationGoalRequest]

@router.post("/calculate_optimization_goal")
async def calculate_opt_goal_endpoint(
    request: OptimizationGoalRequest,
    opt_service: OptimizationService = Depends(get_optimization_service)
):
    try:
        ratios = request.alpha_beta_ratios if request.alpha_beta_ratios else templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]
        
        goal = opt_service.calculate_goal(
            total_eqd2_constraint=request.total_eqd2_constraint,
            organ_name=request.organ_name,
            number_of_fractions=request.number_of_fractions,
            ebrt_dose=request.ebrt_dose,
            ebrt_fractions=request.ebrt_fractions,
            previous_brachy_bed=request.previous_brachy_bed,
            alpha_beta_ratios=ratios
        )
        return JSONResponse(content={"max_d2cc_per_fraction": goal})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# 2. Add this NEW Endpoint
@router.post("/calculate_optimization_goal_batch")
async def calculate_opt_goal_batch_endpoint(
    batch_request: BatchOptimizationGoalRequest,
    opt_service: OptimizationService = Depends(get_optimization_service)
):
    results = []
    try:
        # Process all requests in one go on the server side (much faster)
        for req in batch_request.requests:
            ratios = req.alpha_beta_ratios if req.alpha_beta_ratios else templates["Cervix HDR - EMBRACE II"]["alpha_beta_ratios"]
            
            goal = opt_service.calculate_goal(
                total_eqd2_constraint=req.total_eqd2_constraint,
                organ_name=req.organ_name,
                number_of_fractions=req.number_of_fractions,
                ebrt_dose=req.ebrt_dose,
                ebrt_fractions=req.ebrt_fractions,
                previous_brachy_bed=req.previous_brachy_bed,
                alpha_beta_ratios=ratios
            )
            results.append({
                "Organ": req.organ_name,
                "Total EQD2 Constraint (Gy)": req.total_eqd2_constraint,
                "Max D2cc per Fraction (Gy)": goal
            })
        return JSONResponse(content={"goals": results})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate_pdf")
async def generate_pdf_endpoint(request: PdfGenerationRequest):
    try:
        pdf_bytes = convert_html_to_pdf(request.html_content)
        if pdf_bytes is None:
            raise HTTPException(status_code=500, detail="Failed to generate PDF.")
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=report.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process_plan")
async def process_plan(
    rtplan_file: UploadFile = File(...),
    rtdose_file: UploadFile = File(...),
    rtstruct_file: UploadFile = File(...),
    dvh_text_file: Optional[UploadFile] = File(None),
    previous_brachy_data_json: Optional[str] = Form(None),
    custom_constraints_json: Optional[str] = Form(None),
    selected_point_names_json: Optional[str] = Form(None),
    dose_point_mapping_json: Optional[str] = Form(None),
    num_fractions_delivered: Optional[int] = Form(None),
    ebrt_dose: float = Form(0.0),
    ebrt_fractions: int = Form(1),
    structure_mapping_json: Optional[str] = Form(None),
    confirmed_structure_mapping_json: Optional[str] = Form(None),
    parser_service: ParserService = Depends(get_parser_service)
):
    try:
        # 1. Read and Parse DICOMs and JSON inputs
        rtplan = pydicom.dcmread(io.BytesIO(await rtplan_file.read()))
        rtdose = pydicom.dcmread(io.BytesIO(await rtdose_file.read()))
        rtstruct = pydicom.dcmread(io.BytesIO(await rtstruct_file.read()))

        plan_data = parser_service.get_plan_data(rtplan)
        structure_data = parser_service.get_structure_data(rtstruct)
        
        prev_data = json.loads(previous_brachy_data_json) if previous_brachy_data_json else {}
        constraints = json.loads(custom_constraints_json) if custom_constraints_json else templates["Cervix HDR - EMBRACE II"]
        point_map = json.loads(dose_point_mapping_json) if dose_point_mapping_json else {}
        conf_struct_map = json.loads(confirmed_structure_mapping_json) if confirmed_structure_mapping_json else {}

        ab_ratios = constraints.get("alpha_beta_ratios", {}).copy()
        if "Default" not in ab_ratios: ab_ratios["Default"] = 3.0
        
        planned_fx = plan_data.get('number_of_fractions', 1)
        calc_fx = num_fractions_delivered if num_fractions_delivered is not None else planned_fx

        # 2. Initial DICOM calculation for the CURRENT plan (Digital Twin)
        dvh_from_dicom = calculations.get_dvh(
            rtstruct, rtdose, structure_data, calc_fx,
            ebrt_dose, ebrt_fractions, {}, ab_ratios, conf_struct_map
        )

        # 3. Text file processing and VALIDATION
        tps_warnings = []
        validation_df_records = None
        source_of_truth_dvh = dvh_from_dicom

        if dvh_text_file:
            txt_content = await dvh_text_file.read()
            parsed_data, txt_meta = parser_service.parse_dvh_text_file(txt_content.decode('utf-8'))
            
            if parsed_data:
                dvh_from_text = parser_service.get_dvh_metrics_from_text(
                    parsed_data, conf_struct_map, calc_fx, {}
                )
                
                # VALIDATION: Compare current DICOM calc vs current Text file report
                tps_warnings = validators.validate_tps_import(
                    dvh_from_dicom, dvh_from_text, rtdose.PatientID, txt_meta
                )
                val_df = validators.generate_validation_dataframe(
                    dvh_from_dicom, dvh_from_text, str(rtdose.PatientID)
                )
                validation_df_records = val_df.to_dict('records') if val_df is not None else None
                
                source_of_truth_dvh = dvh_from_text
            else:
                tps_warnings.append("Could not parse uploaded DVH Text File.")

        # 4. Standardize Structure Names for the source of truth
        mapped_source_dvh = {}
        # Use confirmed_structure_mapping_json which is the one from the UI
        for name, data in source_of_truth_dvh.items():
            mapped_name = conf_struct_map.get(name, name)
            if mapped_name and mapped_name != "Ignore":
                mapped_source_dvh[mapped_name] = data
        
        # 5. DOSE SUMMATION
        final_dvh = {}
        all_organ_keys = set(mapped_source_dvh.keys()) | set(prev_data.get("dvh_results", {}).keys())

        for organ in all_organ_keys:
            final_dvh[organ] = {"doses_per_fraction": {}}
            
            previous_doses = prev_data.get("dvh_results", {}).get(organ, {}).get("doses_per_fraction", {})
            current_data = mapped_source_dvh.get(organ, {})
            
            metrics = ['d2cc', 'd1cc', 'd0_1cc', 'd90', 'd98', 'd95', 'max_dose', 'mean_dose', 'min_dose']
            for m in metrics:
                dose_fx_key = f"{m}_gy_per_fraction"
                current_dose_fx = current_data.get(dose_fx_key, 0)
                
                history = previous_doses.get(m, [])
                new_dose_history = history + ([current_dose_fx] * calc_fx)
                
                if new_dose_history:
                    final_dvh[organ]["doses_per_fraction"][m] = new_dose_history
                    
                    alpha_beta = calculations.get_alpha_beta(organ, ab_ratios)
                    total_brachy_bed = sum(d * (1 + d / alpha_beta) for d in new_dose_history if d is not None)
                    
                    bed_ebrt = 0
                    if ebrt_dose > 0 and ebrt_fractions > 0:
                        ebrt_dose_per_fraction = ebrt_dose / ebrt_fractions
                        bed_ebrt = ebrt_dose * (1 + (ebrt_dose_per_fraction / alpha_beta))

                    total_bed = total_brachy_bed + bed_ebrt
                    eqd2 = total_bed / (1 + (2 / alpha_beta))
                    
                    final_dvh[organ][f"bed_{m}"] = round(total_bed, 2)
                    final_dvh[organ][f"eqd2_{m}"] = round(eqd2, 2)

            if 'volume_cc' in current_data:
                final_dvh[organ]['volume_cc'] = current_data['volume_cc']

        # 6. Final evaluation and response construction
        eval_results = calculations.evaluate_constraints(final_dvh, [], constraints.get("constraints", {}).get("target_constraints"), constraints.get("constraints", {}).get("oar_constraints"), constraints.get("point_dose_constraints"), point_map)
        
        response = {
            "patient_name": str(getattr(rtdose, 'PatientName', 'Unknown')),
            "patient_mrn": str(getattr(rtdose, 'PatientID', 'Unknown')),
            "plan_name": plan_data.get('plan_name', 'N/A'),
            "number_of_fractions_delivered": calc_fx,
            "ebrt_dose_input": ebrt_dose,
            "ebrt_fractions_input": ebrt_fractions,
            "dvh_results": final_dvh,
            "constraint_evaluation": eval_results,
            "tps_validation_warnings": tps_warnings,
            "validation_df": validation_df_records
        }
        
        return JSONResponse(content=response)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))