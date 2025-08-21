## Future Enhancements

### User Interface & Experience
- [x] Visual Constraint Indicators
    - [x] Get MD feedback on dose summary
- [ ] Conditional Formatting for Point Dose Results
- [x] Fix the total planned dose column in the report.
- [x] Remove BED in report
- [x] fix contrast on dark mode
- [x] check that you don't have to approve a plan before you can export it.
- [ ] intermediate user input after real-time plan adjustments
- [ ] Customizable Constraints
    - [x] OAR DVH constraints
    - [ ] Target DVH constraints/goals
- [ ] Report Customization
    - [x] fix alpha/beta symbol on report
    - [x] Remove two extra columns on OAR DVH results table from previous constraint status removal
    - [x] Round all reported total planned doses to the same number of decimal points
    - [ ] Dose fx 1, dose fx 2, dose fx 3 etc.
- [x] Templates and Presets for alpha/beta ratios, point selections and dose constraints.
- [ ] Results section be offset color from rest of the UI

### Backend & Calculation Engine
- [ ] Expanded DICOM Support (e.g., CT/MR images)
- [ ] Isodose Line Visualization
- [ ] Advanced Biological Modeling
- [ ] Database Integration
- [ ] Robust Unit Testing
    - [ ] Point Matching
    - [ ] Volume Metric Calculations
    - [ ] Dose Summations
    - [ ] Constraint met visualization
    - [ ] Constraint Template Updates
- [ ] fix point dose reporting and constraint evaluation (need details for point dose constraints eg bladder point, metrics and constraint values)
- [ ] check that the planned number of fractions is correct for plan evaluation
- [x] Display RTPlan info on streamlet plan evaluation summary page - instant second check
- - [ ] Channel Mapping display for catheters (right side of Results) have it look for channel number, channel length, and transfer tube number
    - [x] Refine display format to "Cath X - Chan Y"


### Deployment & Integration
- [ ] Web Application Deployment
- [ ] PACS Integration
- [ ] API for Automation

### Verification
- [ ] Verify "Cylinder HDR" template in config.py: Ensure "Prescription Point" constraint has "check_type": "prescription_tolerance".
