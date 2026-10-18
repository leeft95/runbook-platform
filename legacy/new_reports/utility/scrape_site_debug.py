"""
Script to capture full-page PDF screenshots of HTML reports.
Can scan dashboard links or the entire HTML output folder.
Categorizes by layout type for analysis.
"""
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from collections import defaultdict

from bs4 import BeautifulSoup
from loguru import logger as log
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from ecm.cmds.config import dashboard_path, mk_path
from ecm.cmds.utils import convert_path_to_linux
from ecm.cmds._email import fix_up_html_links

SKIP_PAGES = ["US_Gas_Nominations", "Oil", "SYS"]

SKIP_LAYOUTS = ["other", "error"]

OUTPUT_DIR = Path(r"S:\Michel Kikano\CODE\autoreports\reports\utility\screenshots")

HTML_ROOT = Path(r"S:\Michel Kikano\CODE\outputs\htmls")


def _unrecovered(location):
    """Recovery marker for an expression clipped in the supplied photos."""
    raise NotImplementedError(f"Unrecovered source: {location}")


def get_dashboard_files():
    """Get all k8s dashboard files."""
    dash_path = convert_path_to_linux(Path(dashboard_path))
    dashboard_paths = {}
    for file in dash_path.iterdir():
        if not file.is_dir() and file.stem.endswith("_k8s") and file.suffix == ".htm":
            page_name = file.stem.replace("_k8s", "").replace("LO25_", "")
            log.info(f"Found k8s dashboard: {page_name}")
            dashboard_paths[page_name] = file
    return dashboard_paths


def extract_links_from_dashboards():
    """Extract all page URLs from dashboard files."""
    dashboard_paths = get_dashboard_files()
    all_links = []

    for page_name, file_path in dashboard_paths.items():
        if page_name in SKIP_PAGES:
            continue

        log.info(f"Extracting links from {page_name}")
        fixed_html = fix_up_html_links(file_path.read_text(encoding="utf-8"))
        soup = BeautifulSoup(fixed_html, "html.parser")
        links = soup.find_all("a", href=True)

        for link in links:
            href = link["href"]
            qs = parse_qs(urlsplit(href).query)
            if "page_url" not in qs:
                continue

            href = qs["page_url"][-1]
            temp_path = unquote(unquote(href))

            if sys.platform == "win32":
                temp_path = temp_path.replace("/", "\\")
                if "CODE" in temp_path and not temp_path.startswith("\\CODE"):
                    temp_path = temp_path.split("CODE", 1)[-1]
                    temp_path = "\\CODE" + temp_path
                qualified_path = mk_path + temp_path
            else:
                qualified_path = "/mnt/h" + temp_path

            qualified_path = Path(qualified_path)
            if not qualified_path.exists():
                log.warning(f"{page_name}: File not found - {qualified_path}")
                continue

            link_text = link.text.strip() if link.text else qualified_path.stem
            all_links.append({
                "dashboard": page_name,
                "link_text": link_text,
                "file_path": qualified_path,
            })

    return all_links


def create_chrome_driver():
    """Create a headless Chrome driver for screenshots."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-notifications")
    options.add_argument("--log-level=3")  # Suppress most Chrome logs

    driver = webdriver.Chrome(options=options)
    return driver


def capture_page_to_pdf(driver, file_path, output_path):
    """
    Capture a page to PDF using Chrome's print functionality.

    Args:
        driver: Selenium WebDriver instance
        file_path: Path to the HTML file
        output_path: Path where the PDF will be saved
    """
    import base64

    file_url = f"file:///{str(file_path).replace(chr(92), '/')}"
    log.info(f"Loading: {file_url}")
    driver.get(file_url)

    try:
        driver.execute_script("""
            return new Promise((resolve) => {
                const checkPlotly = () => {
                    if (typeof Plotly === 'undefined') {
                        resolve(true);
                        return;
                    }
                    const plots = document.querySelectorAll('.js-plotly-plot');
                    if (plots.length === 0) {
                        resolve(true);
                        return;
                    }
                    let allRendered = true;
                    plots.forEach(plot => {
                        if (!plot.data || plot.data.length === 0) {
                            allRendered = false;
                        }
                    });
                    if (allRendered) {
                        resolve(true);
                    } else {
                        setTimeout(checkPlotly, 100);
                    }
                };
                setTimeout(checkPlotly, 500);
            });
        """)
        log.debug("Plotly charts rendered")
    except Exception as e:
        log.debug(f"Plotly wait failed: {e}")
        time.sleep(2)

    result = driver.execute_cdp_cmd("Page.printToPDF", {
        "landscape": False,
        "printBackground": True,
        "preferCSSPageSize": True,
        "paperWidth": 11,     # inches (letter width)
        "paperHeight": 17,    # inches (tabloid height for long pages)
        "marginTop": 0.4,
        "marginBottom": 0.4,
        "marginLeft": 0.4,
        "marginRight": 0.4,
        "scale": 0.8,         # Scale down slightly to fit content
    })

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(result["data"]))

    log.info(f"Saved PDF: {output_path}")


def detect_layout_type(html_path):
    """
    Analyze HTML file and detect its layout type based on structure.

    Returns a tuple of (category, details) where category is the main type
    and details contains counts of elements.
    """
    try:
        html_content = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html_content, "html.parser")

        plotly_charts = len(soup.find_all("div", class_="js-plotly-plot")) + len(soup.find_all("div", class_=_unrecovered('IMG_5006 line 194: second Plotly div class')))
        tables = len(soup.find_all("table"))
        iframes = len(soup.find_all("iframe"))
        images = len(soup.find_all("img"))

        has_grid = bool(soup.find(style=lambda x: x and "grid" in x.lower())) if soup.find(style=True) else False
        has_flex = bool(soup.find(style=lambda x: x and "flex" in x.lower())) if soup.find(style=True) else False

        scripts = soup.find_all("script")
        has_plotly_js = any("plotly" in str(s).lower() for s in scripts)

        details = {
            "plotly_charts": plotly_charts,
            "tables": tables,
            "iframes": iframes,
            "images": images,
            "has_plotly_js": has_plotly_js,
        }

        if plotly_charts > 0 and tables > 0:
            category = "charts_and_tables"
        elif plotly_charts > 5:
            category = "multi_chart"
        elif plotly_charts > 0:
            category = "single_chart" if plotly_charts == 1 else "few_charts"
        elif tables > 5:
            category = "multi_table"
        elif tables > 0:
            category = "single_table" if tables == 1 else "few_tables"
        elif iframes > 0:
            category = "iframe_embed"
        elif images > 0:
            category = "image_based"
        elif has_plotly_js:
            category = "dynamic_plotly"  # Has Plotly but charts may be dynamically generated
        else:
            category = "other"

        return category, details

    except Exception as e:
        log.warning(f"Could not analyze {html_path}: {e}")
        return "error", {}


def scan_all_htmls(root_dir=None):
    """
    Recursively scan all HTML files from the root directory.

    Args:
        root_dir: Root directory to scan (default: HTML_ROOT)

    Returns:
        List of Path objects for all HTML files
    """
    if root_dir is None:
        root_dir = HTML_ROOT

    root_dir = Path(root_dir)
    html_files = []

    for pattern in ["*.html", "*.htm"]:
        html_files.extend(root_dir.rglob(pattern))

    log.info(f"Found {len(html_files)} HTML files in {root_dir}")
    return html_files


def convert_all_htmls_to_pdf(output_dir=None, sample_per_category=None):
    """
    Convert all HTML files from HTML_ROOT to PDFs, organized by dashboard and layout type.

    Args:
        output_dir: Directory to save PDFs (default: OUTPUT_DIR / "by_layout")
        sample_per_category: If set, only convert this many per category per dashboard (for sampling)
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / "by_layout"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_files = scan_all_htmls()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    by_dashboard_category = defaultdict(lambda: defaultdict(list))
    log.info(f"Analyzing {len(html_files)} HTML layouts (parallel)...")

    def analyze_file(html_file):
        category, details = detect_layout_type(html_file)
        try:
            rel_path = html_file.relative_to(HTML_ROOT)
            dashboard = rel_path.parts[0] if rel_path.parts else "root"
        except ValueError:
            dashboard = "unknown"
        return html_file, dashboard, category, details

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(analyze_file, f): f for f in html_files}
        done = 0
        for future in as_completed(futures):
            html_file, dashboard, category, details = future.result()
            by_dashboard_category[dashboard][category].append((html_file, details))
            done += 1
            if done % 100 == 0:
                log.info(f"  Analyzed {done}/{len(html_files)} files...")

    log.info("Layout type summary by dashboard:")
    total_to_process = 0
    for dashboard in sorted(by_dashboard_category.keys()):
        categories = by_dashboard_category[dashboard]
        log.info(f"  {dashboard}:")
        for cat, files in sorted(categories.items(), key=lambda x: -len(x[1])):
            count = len(files)
            if cat not in SKIP_LAYOUTS:
                sample_count = min(count, sample_per_category) if sample_per_category else count
                total_to_process += sample_count
            log.info(f"    {cat}: {count} files")

    log.info(f"Total files to process: {total_to_process}")

    import shutil

    driver = create_chrome_driver()
    try:
        for dashboard in sorted(by_dashboard_category.keys()):
            categories = by_dashboard_category[dashboard]

            for category, files in categories.items():
                if category in SKIP_LAYOUTS:
                    log.info(f"Skipping {dashboard}/{category} ({len(files)} files)")
                    continue

                cat_dir = output_dir / dashboard / category
                cat_dir.mkdir(parents=True, exist_ok=True)

                if sample_per_category:
                    files = files[:sample_per_category]

                log.info(f"Processing {dashboard}/{category}: {len(files)} files")

                for html_file, details in files:
                    try:
                        rel_path = html_file.relative_to(HTML_ROOT)
                    except ValueError:
                        rel_path = html_file

                    path_parts = rel_path.parts[1:] if len(rel_path.parts) > 1 else rel_path.parts
                    safe_name = sanitize_filename("_".join(path_parts))
                    base_name = safe_name.rsplit(".", 1)[0]
                    pdf_name = base_name + ".pdf"
                    html_name = base_name + ".html"

                    pdf_path = cat_dir / pdf_name
                    html_copy_path = cat_dir / html_name


                    try:
                        shutil.copy2(str(html_file), str(html_copy_path))
                        capture_page_to_pdf(driver, html_file, pdf_path)
                    except Exception as e:
                        log.error(f"Failed to capture {html_file}: {e}")

    finally:
        driver.quit()

    log.info(f"PDFs saved to: {output_dir}")


def sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames."""
    import re
    name = re.sub(r'\s+', ' ', name).strip()
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "_")
    return name[:100]  # Limit length


def capture_all_screenshots(links, output_dir=None):
    """
    Capture screenshots of all linked pages.

    Args:
        links: List of link dictionaries from extract_links_from_dashboards()
        output_dir: Directory to save screenshots (default: OUTPUT_DIR)
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    driver = create_chrome_driver()
    try:
        for i, link_info in enumerate(links):
            dashboard = link_info["dashboard"]
            link_text = sanitize_filename(link_info["link_text"])
            file_path = link_info["file_path"]

            output_name = f"{dashboard}__{link_text}.pdf"
            output_path = output_dir / output_name

            if output_path.exists():
                log.debug(f"Skipping (already exists): {output_name}")
                continue

            try:
                capture_page_to_pdf(driver, file_path, output_path)
            except Exception as e:
                log.error(f"Failed to capture {file_path}: {e}")

            if (i + 1) % 10 == 0:
                log.info(f"Progress: {i + 1}/{len(links)} screenshots captured")

    finally:
        driver.quit()

    log.info(f"Completed! Screenshots saved to: {output_dir}")


def organize_by_dashboard(output_dir=None):
    """
    Organize existing PDFs into subfolders by dashboard name.

    Moves files like 'EU_Gas_JM__Chart Name.pdf' into 'EU_Gas_JM/Chart Name.pdf'

    Args:
        output_dir: Directory containing the PDFs (default: OUTPUT_DIR)
    """
    import shutil

    if output_dir is None:
        output_dir = OUTPUT_DIR

    output_dir = Path(output_dir)
    if not output_dir.exists():
        log.error(f"Output directory does not exist: {output_dir}")
        return

    moved_count = 0
    for pdf_file in output_dir.glob("*.pdf"):
        parts = pdf_file.stem.split("__", 1)
        if len(parts) != 2:
            log.warning(f"Skipping file with unexpected format: {pdf_file.name}")
            continue

        dashboard_name, link_text = parts

        dashboard_dir = output_dir / dashboard_name
        dashboard_dir.mkdir(exist_ok=True)

        new_path = dashboard_dir / f"{link_text}.pdf"
        shutil.move(str(pdf_file), str(new_path))
        log.debug(f"Moved: {pdf_file.name} -> {dashboard_name}/{link_text}.pdf")
        moved_count += 1

    log.info(f"Organized {moved_count} PDFs into dashboard folders")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Convert HTML reports to PDFs for analysis")
    parser.add_argument("--mode", choices=["dashboard", "all", "sample"], default="sample",
                        help="dashboard: scan dashboard links, all: scan entire HTML folder, sample: 5 per [unrecovered help text]")
    parser.add_argument("--sample-size", type=int, default=5, help="Number of samples per category (for s[unrecovered help text]")
    args = parser.parse_args()

    if args.mode == "dashboard":
        log.info("Scanning dashboard links...")
        links = extract_links_from_dashboards()
        log.info(f"Found {len(links)} links to capture")
        if links:
            capture_all_screenshots(links)
            organize_by_dashboard()
    elif args.mode == "all":
        log.info("Converting ALL HTMLs from root folder...")
        convert_all_htmls_to_pdf(sample_per_category=None)
    else:  # sample
        log.info(f"Converting sample of {args.sample_size} per layout category...")
        convert_all_htmls_to_pdf(sample_per_category=args.sample_size)


if __name__ == "__main__":
    main()
