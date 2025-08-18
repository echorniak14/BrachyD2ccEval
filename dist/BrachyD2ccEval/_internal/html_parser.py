from bs4 import BeautifulSoup

def parse_html_report(file_path):
    """Parses an HTML report and extracts EQD2 values for each organ."""
    eqd2_results = {}
    try:
        with open(file_path, 'r') as f:
            soup = BeautifulSoup(f, 'html.parser')

        # Find the DVH results table
        table = soup.find('h2', string='Dose Volume Histogram (DVH) Results').find_next_sibling('table')
        if not table:
            print("DVH results table not found in HTML report.")
            return eqd2_results

        # Find the headers to get column indices
        headers = [th.get_text(strip=True) for th in table.find('thead').find_all('th')]
        
        organ_col_idx = -1
        eqd2_col_idx = -1
        try:
            organ_col_idx = headers.index('Organ')
            eqd2_col_idx = headers.index('EQD2 (Gy)')
        except ValueError:
            print("Required columns (Organ, EQD2 (Gy)) not found in HTML report.")
            return eqd2_results

        # Extract data from table rows
        for row in table.find('tbody').find_all('tr'):
            cols = row.find_all('td')
            if len(cols) > max(organ_col_idx, eqd2_col_idx):
                organ_name = cols[organ_col_idx].get_text(strip=True)
                eqd2_value_str = cols[eqd2_col_idx].get_text(strip=True)
                try:
                    eqd2_results[organ_name] = float(eqd2_value_str)
                except ValueError:
                    print(f"Could not parse EQD2 value '{eqd2_value_str}' for organ '{organ_name}'. Skipping.")

    except FileNotFoundError:
        print(f"HTML report not found at: {file_path}")
    except Exception as e:
        print(f"Error parsing HTML report {file_path}: {e}")
    
    return eqd2_results

if __name__ == "__main__":
    # Example usage (replace with a path to one of your generated HTML reports)
    example_html_path = "Brachytherapy_Report.html"
    parsed_data = parse_html_report(example_html_path)
    if parsed_data:
        print("Parsed EQD2 data:", parsed_data)
    else:
        print("No data parsed.")
