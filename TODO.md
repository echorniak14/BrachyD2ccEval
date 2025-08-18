## TODO
- improve previous brachy dose summation
- Fix the total planned dose column in the report.
- Dose to meet constraint and constraint met status in DVH results table should use user-input constraints.

- having multiple issues with streamlit displaying the GUI. We were trying to revert the src/streamlit_gui.py to its previous state. Now, I'll comment out the st.data_editor section for constraints in that file but we kept getting failed to edit errors because the exact text in old_string was not found.

## Future Enhancements

### User Interface & Experience
- [ ] Interactive DVH Plots
- [ ] Visual Constraint Indicators
- [ ] Customizable Constraints
- [ ] Batch Processing
- [ ] Report Customization

### Backend & Calculation Engine
- [ ] Expanded DICOM Support (e.g., CT/MR images)
- [ ] Isodose Line Visualization
- [ ] Advanced Biological Modeling
- [ ] Database Integration
- [ ] Robust Unit Testing

### Deployment & Integration
- [ ] Web Application Deployment
- [ ] PACS Integration
- [ ] API for Automation
