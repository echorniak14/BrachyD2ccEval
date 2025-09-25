## Future Enhancements

### User Interface & Experience
- [x] Visual Constraint Indicators
    - [x] Get MD feedback on dose summary
- [x] Conditional Formatting for Point Dose Results
- [x] Fix the total planned dose column in the report.
- [x] Remove BED in report
- [x] fix contrast on dark mode
- [x] check that you don't have to approve a plan before you can export it.
- [ ] intermediate user input after real-time plan adjustments
- [x] Customizable Constraints
    - [x] OAR DVH constraints
    - [x] Target DVH constraints/goals
- [x] Report Customization
    - [x] fix alpha/beta symbol on report
    - [x] Remove two extra columns on OAR DVH results table from previous constraint status removal
    - [x] Round all reported total planned doses to the same number of decimal points
    - [x] Dose fx 1, dose fx 2, dose fx 3 etc.
- [x] Templates and Presets for alpha/beta ratios, point selections and dose constraints.

### Backend & Calculation Engine
- [ ] Database Integration
    - [x] Patient Schedule Review and Dose Summary Fill
    - [x] Planned Delivery Date and Time from RTPLAN?
- [ ] Robust Unit Testing
    - [ ] Point Matching
    - [ ] Volume Metric Calculations
    - [ ] Dose Summations
    - [ ] Constraint met visualization
        - [x] DVH
        - [ ] Points
        - [ ] Dose to meet constraint calculation
    - [x] Constraint Template Updates
- [x] fix point dose reporting and constraint evaluation (need details for point dose constraints eg bladder point, metrics and constraint values)
- [x] check that the planned number of fractions is correct for plan evaluation
- [x] Display RTPlan info on streamlet plan evaluation summary page - instant second check
- [x] Channel Mapping display for catheters (right side of Results) have it look for channel number, channel length, and transfer tube number
- [ ] Dwell time decay dwell position flexibility -> dwell position = index length - 1000.
- [ ] Auto save excel file and pdf and pull up print option
- [x] Flag user if the planned time is outside normal buisness hours
- [ ] Correctly round the dose to meet constraint display in results
- [x] EBRT Dose and number of fractions
- [ ] Use provided previous brachy dose to give optimzation goals to user to achieve ALARA

### Deployment & Integration
## Phase 1: Preparation and Data Gathering
- [x] Gather Data
    - [x] Cylinder Case (3-5)
    - [x] Tandem and Ovoid Case (3-5)
    - [ ] Tandem and Ring Case (3-5)
    - [x] Multichannel Cylinder Case
    - [ ] Interstitial Case
- [ ] Document the manual process
- [ ] Create the Data collection Spreadsheet
    - [ ] Patient ID
    - [ ] Metric Evaluated
    - [ ] Manual Result
    - [ ] App Result
    - [ ] Absolute Difference
    - [ ] Percent Difference
    - [ ] Manual Time (sec)
    - [ ] App Time (sec)

## Phase 2: Execution and Testing
- [ ] Perform Manual Analysis for All Cases
    - [ ] time the manual process from start to finish and record it
    - [ ] Save the spreadsheets used for manual analysis in the appropriate folders
- [ ] Perform Application Analysis for All Cases
    - [ ] time the application process from start to finish and record it
    - [ ] Save the JSON files in the appropriate folders

## Phase 3: Analysis and Release Report
- [ ] Analyze collected data
    - [ ] Define an acceptance tolerance (e.g., < 2% for dosimetric values)
    - [ ] Calculate the average time saved per case and the overall efficiency improvement
- [ ] Write the Release Report
    - [ ] 1.0 Purpose: State the goal of the validation.
    - [ ] 2.0 Methodology: Describe the test cases, manual process, and acceptance criteria
    - [ ] 3.0 Validation Results: Include the summary table and a conclusion on dosimetric accuracy
    - [ ] 4.0 Efficiency Analysis: Present the timing comparison and discuss benefits
    - [ ] 5.0 Conclusion and Recommendation: Summarize findings and formally recommend for clinical implementation

- [ ] Web Application Deployment
- [ ] PACS Integration
- [ ] API for Automation