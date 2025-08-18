import xlrd

workbook = xlrd.open_workbook(r"C:\Users\echorniak\GIT\BrachyD2ccEval\ABS LQ spread sheet v2.1_Completed.xls")

def get_d2cc(sheet_name):
    sheet = workbook.sheet_by_name(sheet_name)
    return sheet.cell_value(11, 1)

print("| Organ   | D2cc (Script) | D2cc (Spreadsheet) |")
print("|---------|---------------|--------------------|")

# Bladder
print(f"| Bladder | 3.69          | {get_d2cc('Bladder')}              |")

# Rectum
print(f"| Rectum  | 2.31          | {get_d2cc('Rectum')}              |")

# Sigmoid
print(f"| Sigmoid | 4.97          | {get_d2cc('Sigmoid')}              |")

# Bowel
print(f"| Bowel   | 1.54          | {get_d2cc('Bowel')}              |")
