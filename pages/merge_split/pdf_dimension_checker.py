import fitz  # PyMuPDF
import os
from pathlib import Path
from typing import List, Tuple, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def check_single_pdf_dimensions(pdf_path: str) -> Dict:
    """
    Check if all pages in a single PDF have the same dimensions.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dict with results:
        {
            'file_path': str,
            'file_name': str,
            'total_pages': int,
            'all_same': bool,
            'dimensions': List[Tuple[int, int]],  # List of (width, height) for each page
            'unique_dimensions': Set[Tuple[int, int]],  # Set of unique dimensions found
            'error': str or None
        }
    """
    result = {
        'file_path': pdf_path,
        'file_name': os.path.basename(pdf_path),
        'total_pages': 0,
        'all_same': True,
        'dimensions': [],
        'unique_dimensions': set(),
        'error': None
    }
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        result['total_pages'] = total_pages
        
        if total_pages == 0:
            result['error'] = "PDF has no pages"
            doc.close()
            return result
        
        # Get dimensions of all pages
        dimensions = []
        for page_num in range(total_pages):
            try:
                page = doc[page_num]
                rect = page.rect
                width = int(round(rect.width))
                height = int(round(rect.height))
                dimensions.append((width, height))
            except Exception as e:
                result['error'] = f"Error reading page {page_num + 1}: {str(e)}"
                doc.close()
                return result
        
        doc.close()
        
        # Analyze dimensions
        result['dimensions'] = dimensions
        unique_dimensions = set(dimensions)
        result['unique_dimensions'] = unique_dimensions
        result['all_same'] = len(unique_dimensions) == 1
        
    except Exception as e:
        result['error'] = f"Error opening PDF: {str(e)}"
    
    return result


def check_pdf_dimensions_threaded(pdf_path: str, progress_callback=None) -> Dict:
    """
    Check PDF dimensions with progress callback for GUI updates.
    
    Args:
        pdf_path: Path to the PDF file
        progress_callback: Function to call with (percent, message) updates
        
    Returns:
        Same as check_single_pdf_dimensions
    """
    if progress_callback:
        progress_callback(0, "Opening PDF...")
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        if progress_callback:
            progress_callback(10, f"PDF has {total_pages} pages")
        
        if total_pages == 0:
            doc.close()
            return {
                'file_path': pdf_path,
                'file_name': os.path.basename(pdf_path),
                'total_pages': 0,
                'all_same': True,
                'dimensions': [],
                'unique_dimensions': set(),
                'error': "PDF has no pages"
            }
        
        # Check dimensions with progress updates
        dimensions = []
        unique_dimensions = set()
        
        for page_num in range(total_pages):
            if progress_callback:
                progress = 10 + int((page_num / total_pages) * 80)
                progress_callback(progress, f"Checking page {page_num + 1}/{total_pages}")
            
            try:
                page = doc[page_num]
                rect = page.rect
                width = int(round(rect.width))
                height = int(round(rect.height))
                dimensions.append((width, height))
                unique_dimensions.add((width, height))
            except Exception as e:
                doc.close()
                return {
                    'file_path': pdf_path,
                    'file_name': os.path.basename(pdf_path),
                    'total_pages': total_pages,
                    'all_same': False,
                    'dimensions': dimensions,
                    'unique_dimensions': unique_dimensions,
                    'error': f"Error reading page {page_num + 1}: {str(e)}"
                }
        
        doc.close()
        
        if progress_callback:
            progress_callback(95, "Analyzing results...")
        
        all_same = len(unique_dimensions) == 1
        
        if progress_callback:
            progress_callback(100, "Dimension check complete")
        
        return {
            'file_path': pdf_path,
            'file_name': os.path.basename(pdf_path),
            'total_pages': total_pages,
            'all_same': all_same,
            'dimensions': dimensions,
            'unique_dimensions': unique_dimensions,
            'error': None
        }
        
    except Exception as e:
        if progress_callback:
            progress_callback(100, "Error occurred")
        return {
            'file_path': pdf_path,
            'file_name': os.path.basename(pdf_path),
            'total_pages': 0,
            'all_same': False,
            'dimensions': [],
            'unique_dimensions': set(),
            'error': f"Error opening PDF: {str(e)}"
        }


def format_dimensions(dimensions: Tuple[int, int]) -> str:
    """
    Format dimensions tuple to human-readable string.
    
    Args:
        dimensions: Tuple of (width, height) in points
        
    Returns:
        Formatted string like "210×297 mm (595×842 pt)"
    """
    width_pt, height_pt = dimensions
    
    # Convert points to mm (1 point = 0.352778 mm)
    width_mm = round(width_pt * 0.352778, 1)
    height_mm = round(height_pt * 0.352778, 1)
    
    return f"{width_mm}×{height_mm} mm ({width_pt}×{height_pt} pt)"


def get_dimension_summary(result: Dict) -> str:
    """
    Get a summary string of the dimension check results.
    
    Args:
        result: Result from check_single_pdf_dimensions or check_pdf_dimensions_threaded
        
    Returns:
        Summary string
    """
    if result['error']:
        return f"Error: {result['error']}"
    
    if result['all_same']:
        if result['unique_dimensions']:
            dim = list(result['unique_dimensions'])[0]
            return f"All {result['total_pages']} pages have same dimensions: {format_dimensions(dim)}"
        else:
            return "No pages found"
    else:
        unique_count = len(result['unique_dimensions'])
        return f"Found {unique_count} different page sizes in {result['total_pages']} pages"


def check_folder_pdf_dimensions(folder_path: str) -> Tuple[bool, Tuple[int, int], List[str], Dict[str, Tuple[int, int]]]:
    """
    Check dimensions of all PDFs in a folder.
    
    Args:
        folder_path: Path to folder containing PDFs
        
    Returns:
        Tuple of:
        - all_same: bool (True if all PDFs have same dimensions)
        - ref_size: Tuple[int, int] (reference dimensions)
        - differing: List[str] (list of filenames with different dimensions)
        - file_main: Dict[str, Tuple[int, int]] (filename -> dimensions mapping)
    """
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        return True, (0, 0), [], {}
    
    file_main = {}
    all_dimensions = set()
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(folder_path, pdf_file)
        try:
            result = check_single_pdf_dimensions(pdf_path)
            if not result['error'] and result['unique_dimensions']:
                # Use the first dimension found in the PDF
                dim = list(result['unique_dimensions'])[0]
                file_main[pdf_file] = dim
                all_dimensions.add(dim)
        except Exception:
            continue
    
    if not all_dimensions:
        return True, (0, 0), [], file_main
    
    # Check if all PDFs have the same dimensions
    if len(all_dimensions) == 1:
        ref_size = list(all_dimensions)[0]
        return True, ref_size, [], file_main
    else:
        # Find the most common dimension as reference
        dimension_counts = {}
        for dim in all_dimensions:
            count = sum(1 for d in file_main.values() if d == dim)
            dimension_counts[dim] = count
        
        ref_size = max(dimension_counts, key=dimension_counts.get)
        
        # Find files with different dimensions
        differing = [filename for filename, dim in file_main.items() if dim != ref_size]
        
        return False, ref_size, differing, file_main


def format_points_to_mm(dimensions: Tuple[int, int]) -> str:
    """
    Convert dimensions from points to mm and format as string.
    
    Args:
        dimensions: Tuple of (width, height) in points
        
    Returns:
        Formatted string like "210×297 mm"
    """
    width_pt, height_pt = dimensions
    
    # Convert points to mm (1 point = 0.352778 mm)
    width_mm = round(width_pt * 0.352778, 1)
    height_mm = round(height_pt * 0.352778, 1)
    
    return f"{width_mm}×{height_mm} mm"


if __name__ == "__main__":
    # Test the functions
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        result = check_pdf_dimensions_threaded(pdf_path, print)
        print(f"\nResults for {result['file_name']}:")
        print(f"Total pages: {result['total_pages']}")
        print(f"All same dimensions: {result['all_same']}")
        print(f"Summary: {get_dimension_summary(result)}")
        
        if result['unique_dimensions']:
            print("\nUnique dimensions found:")
            for dim in result['unique_dimensions']:
                print(f"  - {format_dimensions(dim)}")
    else:
        print("Usage: python pdf_dimension_checker.py <pdf_file_path>")
