import os
from typing import Dict, List, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed


def _round_size(size_tuple: Tuple[float, float]) -> Tuple[int, int]:
    """Round to nearest integer point to avoid float noise."""
    return (int(round(size_tuple[0])), int(round(size_tuple[1])))


def _get_pdf_unique_page_sizes(pdf_path: str, sample_size: int = 10) -> Set[Tuple[int, int]]:
    """Extract unique page sizes from a PDF (samples random pages if PDF is large)."""
    import fitz  # PyMuPDF
    import random
    
    sizes: Set[Tuple[int, int]] = set()
    doc = None
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # If PDF has fewer pages than sample_size, check all pages
        if total_pages <= sample_size:
            pages_to_check = range(total_pages)
        else:
            # Randomly sample pages
            pages_to_check = random.sample(range(total_pages), sample_size)
        
        for page_num in pages_to_check:
            page = doc[page_num]
            r = page.rect
            sizes.add(_round_size((r.width, r.height)))
    except Exception:
        return set()
    finally:
        if doc is not None:
            doc.close()
    return sizes


def _process_single_pdf(args: Tuple[str, str, int]) -> Tuple[str, Set[Tuple[int, int]]]:
    folder_path, filename, sample_size = args
    full_path = os.path.join(folder_path, filename)
    sizes = _get_pdf_unique_page_sizes(full_path, sample_size)
    return filename, sizes


def check_folder_pdf_dimensions(folder_path: str, max_workers: int = None, sample_size: int = 10):
    """
    Analyze all PDFs in a folder and determine if their page sizes match.
    Uses ThreadPoolExecutor for parallel processing of PDFs.

    Args:
        folder_path: Path to the folder containing PDF files
        max_workers: Maximum number of threads (None = uses default based on CPU count)

    Returns:
        - all_same: True if every page of every PDF shares the exact same size
        - reference_size: The common size (width, height) in points if all_same else (0, 0)
        - differing_files: List of PDF filenames that contain pages with sizes
                          different from the reference or have multiple sizes internally
        - file_main_sizes: Mapping filename -> a representative size (first unique size) for display
    """
    # Validate folder path
    if not os.path.isdir(folder_path):
        return False, (0, 0), [], {}

    # Get all PDF files
    pdf_files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        return False, (0, 0), [], {}

    # Process PDFs in parallel
    per_file_sizes: Dict[str, Set[Tuple[int, int]]] = {}
    file_main_sizes: Dict[str, Tuple[int, int]] = {}
    
    # Prepare arguments for parallel processing
    # Include sample_size so the worker can control how many pages to sample
    tasks = [(folder_path, filename, sample_size) for filename in pdf_files]
    
    # Use ThreadPoolExecutor for I/O-bound PDF reading
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {executor.submit(_process_single_pdf, task): task[1] for task in tasks}
        
        # Collect results as they complete
        for future in as_completed(future_to_file):
            try:
                filename, sizes = future.result()
                per_file_sizes[filename] = sizes
                
                # Choose a representative size (first from sorted set) for display
                if sizes:
                    file_main_sizes[filename] = sorted(list(sizes))[0]
                else:
                    file_main_sizes[filename] = (0, 0)
            except Exception:
                # If processing failed, mark as unknown
                filename = future_to_file[future]
                per_file_sizes[filename] = set()
                file_main_sizes[filename] = (0, 0)

    # Handle edge case: no valid PDFs processed
    if not per_file_sizes:
        return False, (0, 0), [], {}

    # Determine reference size: use the most common size across all files/pages
    from collections import Counter
    all_sizes = []
    for sizes in per_file_sizes.values():
        all_sizes.extend(list(sizes))
    
    if not all_sizes:
        return False, (0, 0), list(per_file_sizes.keys()), file_main_sizes

    size_counts = Counter(all_sizes)
    reference_size, _ = size_counts.most_common(1)[0]

    # Identify differing files
    differing_files: List[str] = []
    all_same = True

    for name, sizes in per_file_sizes.items():
        # File differs if: no sizes, multiple sizes, or doesn't contain reference size
        if not sizes or len(sizes) > 1 or reference_size not in sizes:
            differing_files.append(name)
            all_same = False

    return all_same, reference_size, differing_files, file_main_sizes


def format_points_to_mm(size_points: Tuple[int, int]) -> str:
    """Convert PDF points to millimeters for human-readable display."""
    # 1 point = 1/72 inch; 1 inch = 25.4 mm
    w_pt, h_pt = size_points
    w_mm = round(w_pt * 25.4 / 72.0)
    h_mm = round(h_pt * 25.4 / 72.0)
    return f"{w_mm} × {h_mm} mm"