## Future Enhancements

### User Interface & Experience
- [x] Visual Constraint Indicators
    - [ ] Get MD feedback on dose summary
- [ ] Conditional Formatting for Point Dose Results
- [x] Fix the total planned dose column in the report.
- [x] Remove BED in report
- [x] fix contrast on dark mode
- [x] check that you don't have to approve a plan before you can export it.
- [ ] intermediate user input after real-time plan adjustments
- [x] Customizable Constraints
- [ ] Batch Processing
- [ ] Report Customization
    - [x] fix alpha/beta symbol on report
    - [x] Remove two extra columns on OAR DVH results table from previous constraint status removal
    - [x] Round all reported total planned doses to the same number of decimal points
- [x] Templates and Presets for alpha/beta ratios, point selections and dose constraints.
- [ ] Investigate and fix the indentation of min/max dose constraints in the Streamlit GUI.

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

### Deployment & Integration
- [ ] Web Application Deployment
- [ ] PACS Integration
- [ ] API for Automation