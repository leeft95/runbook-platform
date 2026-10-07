"""
Extract all tables/figures from certain page of EA US Oil Weekly PDF
and save them as dataframes - IMPROVED VERSION with area-based extraction
"""

import pandas as pd
import tabula
from pathlib import Path
import re


def _missing_photo_text(lines):
    raise NotImplementedError(f"Transcription gap in ea_pdf_improved.py, photographed lines {lines}")


def extract_all_tables_from_page(pdf_path, page_num=2):
    """
    Extract all tables (Fig 1, Fig 2, etc.) from a specified page of the PDF using area-based extraction
    Returns a dictionary of dataframes
    """
    print(f"Extracting all tables from page {page_num}...")
    page_areas = {
        2: [([10, 0, 350, 612], "Fig 1"), ([340, 0, 792, 612], "Fig 2")],
        3: [([10, 0, 396, 612], "Fig 3"), ([396, 0, 792, 612], "Fig 4")],
        4: [([10, 0, 280, 612], "Fig 5"), ([280, 0, 540, 612], "Fig 6")],
        5: [([10, 0, 280, 612], "Fig 9"), ([280, 0, 540, 612], "Fig 10")],
        7: [([10, 0, 396, 612], "Fig 17"), ([396, 0, 792, 612], "Fig 18")],
        8: [([10, 0, 396, 612], "Fig 19"), ([396, 0, 792, 612], "Fig 20")],
        9: [([10, 0, 396, 612], "Fig 21"), ([396, 0, 792, 612], "Fig 22")],
        10: [([10, 0, 396, 612], "Fig 23"), ([396, 0, 792, 612], "Fig 24")],
        11: [([10, 0, 396, 612], "Fig 25"), ([396, 0, 792, 612], "Fig 26")],
    }
    processed_tables = {}
    if page_num in page_areas:
        for area, expected_fig in page_areas[page_num]:
            try:
                df = tabula.read_pdf(pdf_path, pages=page_num, multiple_tables=False, stream=True,
                                     area=area, pandas_options={'header': None})
                if isinstance(df, list) and len(df) > 0:
                    df = df[0]
                if df is not None and not df.empty:
                    df = df.dropna(how='all', axis=0)
                    df = df.dropna(how='all', axis=1)
                    df = df.reset_index(drop=True)
                    fig_pattern = re.compile(r'Fig\s+(\d+):', re.IGNORECASE)
                    fig_found = None
                    for idx, row in df.iterrows():
                        for col_idx in range(len(row)):
                            cell_val = str(row.iloc[col_idx]).strip() if pd.notna(row.iloc[col_idx]) else ""
                            fig_match = fig_pattern.search(cell_val)
                            if fig_match:
                                fig_found = f"Fig {fig_match.group(1)}"
                                break
                        if fig_found:
                            break
                    fig_name = fig_found if fig_found else expected_fig
                    processed_tables[fig_name] = df
                    print(f"--- {fig_name} ---")
                    print(f"Rows: {len(df)}")
                    print(df.head())
                    print()
            except Exception as e:
                print(f"Error extracting {expected_fig}: {e}")
    else:
        print(f"No predefined areas for page {page_num}, using default extraction...")
        tables = tabula.read_pdf(pdf_path, pages=page_num, multiple_tables=True, stream=True,
                                 pandas_options={'header': None})
        fig_pattern = re.compile(r'Fig\s+(\d+):', re.IGNORECASE)
        for table_idx, df in enumerate(tables):
            if df.empty:
                continue
            df = df.dropna(how='all', axis=0)
            df = df.dropna(how='all', axis=1)
            df = df.reset_index(drop=True)
            current_fig = None
            start_idx = None
            for idx, row in df.iterrows():
                fig_match = None
                for col_idx in range(len(row)):
                    cell_val = str(row.iloc[col_idx]).strip() if pd.notna(row.iloc[col_idx]) else ""
                    fig_match = fig_pattern.search(cell_val)
                    if fig_match:
                        break
                if fig_match:
                    if current_fig is not None and start_idx is not None:
                        table_df = df.iloc[start_idx:idx].copy()
                        table_df = table_df.reset_index(drop=True)
                        processed_tables[current_fig] = table_df
                        print(f"--- {current_fig} ---")
                        print(f"Rows: {len(table_df)}")
                        print(table_df.head())
                        print()
                    fig_num = fig_match.group(1)
                    current_fig = f"Fig {fig_num}"
                    start_idx = idx
                elif current_fig is not None and start_idx is not None:
                    row_text = ' '.join([str(val) for val in row if pd.notna(val)]).lower()
                    if 'source:' in row_text:
                        table_df = df.iloc[start_idx:idx+1].copy()
                        table_df = table_df.reset_index(drop=True)
                        processed_tables[current_fig] = table_df
                        print(f"--- {current_fig} ---")
                        print(f"Rows: {len(table_df)}")
                        print(table_df.head())
                        print()
                        current_fig = None
                        start_idx = None
            if current_fig is not None and start_idx is not None:
                table_df = df.iloc[start_idx:].copy()
                table_df = table_df.reset_index(drop=True)
                processed_tables[current_fig] = table_df
                print(f"--- {current_fig} ---")
                print(f"Rows: {len(table_df)}")
                print(table_df.head())
                print()
    print(f"Total extracted: {len(processed_tables)} table(s)\n")
    return processed_tables


def simple_processing_table(df):
    new_df = df.copy()
    new_df.dropna(how='all', axis=1, inplace=True)  # Remove empty columns
    fig_row = None
    for idx, row in new_df.iterrows():
        cell_val = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if cell_val.startswith('Fig'):
            fig_row = idx
            break
    source_row = None
    for idx, row in new_df.iterrows():
        row_text = ' '.join([str(val) for val in row if pd.notna(val)]).lower()
        if 'source:' in row_text:
            source_row = idx
            break
    if fig_row is not None and source_row is not None:
        new_df = new_df.iloc[fig_row:source_row+1, :].reset_index(drop=True)
    new_df.dropna(how='all', axis=1, inplace=True)  # Remove empty columns
    if len(new_df) > 1:
        new_df.columns = new_df.iloc[1, :]
        new_df = new_df.iloc[2:-1, :].reset_index(drop=True)  # Remove Fig row, header row, and Source row
    for col in new_df.columns[1:]:
        new_df[col] = new_df[col].astype(str).str.replace(',', '', regex=False)  # Remove commas
        new_df[col] = new_df[col].astype(str).str.replace(r'\(([\d.]+)\)', r'-\1', regex=True)
        new_df[col] = pd.to_numeric(new_df[col], errors='coerce')
    return new_df


def split_month_columns(df, date_format="%b%y"):
    """
    Split any columns that contain multiple months into separate columns
    E.g., if a cell has "Jan Feb Mar", split into 3 columns with one month each
    Ignores first row (with "Fig") and last row (with "Source")

    Special handling for column 0: separates name from first month using rpartition on last space
    """
    if len(df) <= 2:
        return df  # Not enough rows to process
    fig_row = None
    for idx, row in df.iterrows():
        cell_val = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if 'Fig' in cell_val:
            fig_row = idx
            break
    if fig_row is not None and fig_row > 0:
        df = df.iloc[fig_row:, :].reset_index(drop=True)
    source_row = None
    for idx, row in df.iterrows():
        row_text = ' '.join([str(val) for val in row if pd.notna(val)]).lower()
        if 'source:' in row_text:
            source_row = idx
            break
    if source_row is not None and source_row < len(df) - 1:
        df = df.iloc[:source_row+1, :].reset_index(drop=True)
    if len(df) <= 2:
        return df  # Not enough rows to process after dropping
    if date_format in ["%b%y"]:
        month_pattern = re.compile(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{2})', re.IGNORECASE)
    elif date_format in ["%d%b"]:
        month_pattern = re.compile(r'(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', re.IGNORECASE)
    columns_to_split = {}
    for col_idx in range(len(df.columns)):
        val_str = str(df.iloc[1, col_idx])
        columns_to_split[col_idx] = [' '.join(match) for match in month_pattern.findall(val_str)]
    if not columns_to_split:
        return df  # No columns need splitting
    print(f"\nSplitting columns with multiple months: {columns_to_split}")
    col0_data = []
    col0_names = []
    col0_first_month = []
    all_month_cols = []
    extent_first_column = False
    for k, v in columns_to_split.items():
        if k == 0 and len(v) == 0:
            col0_names = df.iloc[:, 0].tolist()
        else:
            for split_idx in range(len(v)):
                month_col = []
                for idx in range(len(df)):
                    if idx < 2 or idx == len(df) - 1:
                        if idx == 1:
                            if k == 0 and split_idx == 0:
                                col0_names.append("Name")
                            month_col.append(v[split_idx])
                        else:
                            if k == 0 and split_idx == 0:
                                col0_names.append(None)
                            month_col.append(None)
                    else:
                        row_val = df.iloc[idx, k]
                        parts = str(row_val).split()
                        if k == 0:
                            if idx == 2 and len(parts) <= len(v) and len(columns_to_split[k+1]) == 0:
                                extent_first_column = True
                            if extent_first_column:
                                parts += str(df.iloc[idx, k+1]).split()
                            if split_idx == 0:
                                col0_names.append(' '.join(parts[:len(parts)-len(v)]))  # everything after f [clipped original inline comment]
                            month_col.append(parts[len(parts)-len(v)+split_idx])
                        else:
                            if split_idx < len(parts) and len(parts) == len(v):
                                if k < len(columns_to_split)-1 and len(columns_to_split[k+1]) == 0 and _missing_photo_text('293: pd.is... predicate'):
                                    month_col.append(df.iloc[idx, k+1])
                                else:
                                    month_col.append(parts[split_idx])
                            else:
                                if len(parts) < len(v):
                                    month_col.append(df.iloc[idx, k+1].split(' ')[0] if (k+1) in df.columns else _missing_photo_text('300: conditional fallback'))
                                elif len(parts) > len(v):
                                    month_col.append(parts[-1])
                                else:
                                    month_col.append(None)
                all_month_cols.append(month_col)
    new_df = pd.DataFrame()
    new_df.insert(0, 'Name', col0_names)
    for i, month_col in enumerate(all_month_cols):
        new_df.insert(len(new_df.columns), f'Month_{i+1}', month_col)
    new_df.columns = new_df.iloc[1, :]  # Set first row as header
    new_df = new_df.iloc[2:-1, :].reset_index(drop=True)  # Remove first and last rows
    for col in new_df.columns[1:]:
        new_df[col] = new_df[col].astype(str).str.replace(',', '', regex=False)  # Remove commas
        new_df[col] = new_df[col].astype(str).str.replace(r'\(([\d.]+)\)', r'-\1', regex=True)
        new_df[col] = pd.to_numeric(new_df[col], errors='coerce')
    return new_df


def extract_one_pdf(pdf_path, excel_path):
    tables = {}
    tables_p2 = extract_all_tables_from_page(pdf_path, page_num=2)
    tables_p2["Fig 1"] = simple_processing_table(tables_p2["Fig 1"])
    tables_p2["Fig 2"] = split_month_columns(tables_p2["Fig 2"])
    tables.update(tables_p2)
    tables_p3 = extract_all_tables_from_page(pdf_path, page_num=3)
    tables_p3["Fig 3"] = split_month_columns(tables_p3["Fig 3"])
    tables_p3["Fig 4"] = split_month_columns(tables_p3["Fig 4"])
    tables.update(tables_p3)
    tables_p4 = extract_all_tables_from_page(pdf_path, page_num=4)
    tables_p4["Fig 5"] = split_month_columns(tables_p4["Fig 5"])
    tables_p4["Fig 6"] = split_month_columns(tables_p4["Fig 6"], date_format="%d%b")
    tables.update(tables_p4)
    tables_p5 = extract_all_tables_from_page(pdf_path, page_num=5)
    tables_p5["Fig 9"] = split_month_columns(tables_p5["Fig 9"])
    tables_p5["Fig 10"] = split_month_columns(tables_p5["Fig 10"], date_format="%d%b")
    tables.update(tables_p5)
    tables_p7 = extract_all_tables_from_page(pdf_path, page_num=7)
    tables_p7["Fig 17"] = split_month_columns(tables_p7["Fig 17"])
    tables_p7["Fig 18"] = split_month_columns(tables_p7["Fig 18"])
    tables.update(tables_p7)
    tables_p8 = extract_all_tables_from_page(pdf_path, page_num=8)
    tables_p8["Fig 19"] = split_month_columns(tables_p8["Fig 19"])
    tables_p8["Fig 20"] = split_month_columns(tables_p8["Fig 20"])
    tables.update(tables_p8)
    tables_p9 = extract_all_tables_from_page(pdf_path, page_num=9)
    tables_p9["Fig 21"] = split_month_columns(tables_p9["Fig 21"])
    tables_p9["Fig 22"] = split_month_columns(tables_p9["Fig 22"])
    tables.update(tables_p9)
    tables_p10 = extract_all_tables_from_page(pdf_path, page_num=10)
    tables_p10["Fig 23"] = split_month_columns(tables_p10["Fig 23"])
    tables_p10["Fig 24"] = split_month_columns(tables_p10["Fig 24"])
    tables.update(tables_p10)
    tables_p11 = extract_all_tables_from_page(pdf_path, page_num=11)
    tables_p11["Fig 25"] = split_month_columns(tables_p11["Fig 25"])
    tables_p11["Fig 26"] = split_month_columns(tables_p11["Fig 26"])
    tables.update(tables_p11)
    key_map = {
        "Fig 1": "Fig 1 US inventory projections",
        "Fig 2": "Fig 2 Cushing balances",
        "Fig 3": "Fig 3 US crude oil balance 2025",
        "Fig 4": "Fig 4 US crude oil balance 2026",
        "Fig 5": "Fig 5 US gasoline balance",
        "Fig 6": "Fig 6 US gasoline balance weekly forecast",
        "Fig 9": "Fig 9 US distillate balance",
        "Fig 10": "Fig 10 US distillate balance weekly forecast",
        "Fig 17": "Fig 17 PADD 1 crude oil balance 2025",
        "Fig 18": "Fig 18 PADD 1 crude oil balance 2026",
        "Fig 19": "Fig 19 PADD 2 crude oil balance 2025",
        "Fig 20": "Fig 20 PADD 2 crude oil balance 2026",
        "Fig 21": "Fig 21 PADD 3 crude oil balance 2025",
        "Fig 22": "Fig 22 PADD 3 crude oil balance 2026",
        "Fig 23": "Fig 23 PADD 4 crude oil balance 2025",
        "Fig 24": "Fig 24 PADD 4 crude oil balance 2026",
        "Fig 25": "Fig 25 PADD 5 crude oil balance 2025",
        "Fig 26": "Fig 26 PADD 5 crude oil balance 2026",
    }
    tables = {k: v for k, v in tables.items() if k in key_map}
    for old_key, new_key in key_map.items():
        tables[new_key] = tables.pop(old_key)
    pdf_name = Path(pdf_path).stem
    output_dir = Path(excel_path).parent
    output_file = excel_path / f"{pdf_name}.xlsx"
    print(f"\nSaving tables to Excel: {output_file}")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for table_name, df in tables.items():
            df.to_excel(writer, sheet_name=table_name, index=False)
            print(f"  - Saved '{table_name}'")
    print(f"\n✓ Successfully saved {len(tables)} table(s) to: {output_file}")
    return tables


def update():
    pdf_folder = Path(r"s:\Michel Kikano\CODE\data\EA\US Oil Weekly")
    excel_folder = Path(r"s:\Michel Kikano\CODE\outputs\csvs\oil\ea\US Oil Weekly")
    pdf_files = list(pdf_folder.glob("*.pdf"))
    for pdf_file in pdf_files:
        excel_file = excel_folder / f"{pdf_file.stem}.xlsx"
        if not excel_file.exists():
            extract_one_pdf(pdf_file, excel_folder)
            print(f"  - Extracted and saved: {excel_file}")


if __name__ == "__main__":
    update()
