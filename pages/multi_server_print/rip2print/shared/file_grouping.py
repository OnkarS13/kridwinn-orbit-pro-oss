"""
File Grouping Utility for Multi-PDF RIP Files

This module provides utilities to group RIP files by their original PDF/image name.

RIP Filename Pattern:
    {ORIGINAL_IMAGE_NAME}_rip_{SERIAL_NUMBER}_{COLOR}.ext

Example:
    TEST_File_1709_page_0017_rip_0017_0.bmp
    └────────┬────────────┘ └─┬─┘ └─┬─┘ └┬┘
             │               │    │   └─ Color: 0
             │               │    └───── Serial: 0017
             │               └────────── Keyword: _rip_
             └────────────────────────── Original image name (GROUP KEY)
"""

from pathlib import Path
from typing import List, Dict
import re


def natural_sort_key(filename: str):
    """
    Natural sorting key for filenames with numbers.
    
    Ensures files are sorted as: 1, 2, 3... 10, 11, 12
    instead of: 1, 10, 11, 12, 2, 3...
    
    Args:
        filename: Filename to generate sort key for
        
    Returns:
        List of strings and integers for natural sorting
        
    Examples:
        >>> sorted(['page_1.tif', 'page_10.tif', 'page_2.tif'], key=natural_sort_key)
        ['page_1.tif', 'page_2.tif', 'page_10.tif']
    """
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', filename)]


def extract_group_prefix(filename: str) -> str:
    """
    Extract PDF group prefix from RIP filename using intelligent pattern detection.
    
    This function handles multiple naming patterns:
    1. With _rip_ keyword: {NAME}_rip_{SERIAL}_{COLOR}.ext
    2. Without _rip_: {NAME}_{PAGE}_{COLOR}.ext
    3. With page_XXXX: {NAME}_page_{PAGE}_rip_{SERIAL}_{COLOR}.ext
    
    The algorithm intelligently removes page numbers and color separations while
    preserving the core document identifier.
    
    Args:
        filename: RIP filename with extension
        
    Returns:
        Group prefix (document identifier without page/color info)
        
    Examples:
        >>> extract_group_prefix("TEST_70mm_rip_0005_0.bmp")
        'TEST_70mm'
        >>> extract_group_prefix("TEST_File_1709_page_0017_rip_0017_0.bmp")
        'TEST_File_1709'
        >>> extract_group_prefix("Text_1_A_rip_0001_0.tif")
        'Text_1_A'
        >>> extract_group_prefix("TEST_70mm_8_0.tif")
        'TEST_70mm'
    """
    import re
    
    # Remove extension
    name = Path(filename).stem
    
    # Strategy 1: If contains "_rip_", split there first
    if "_rip_" in name:
        # Get everything before _rip_
        base_name = name.split('_rip_')[0]
        
        # Now check if base_name has page_XXXX pattern and remove it
        # Pattern: anything ending with _page_DIGITS or _page_DIGITS_more
        # Examples: 
        #   TEST_File_1709_page_0017 -> TEST_File_1709
        #   Document_page_5 -> Document
        #   Report_2024_page_001 -> Report_2024
        
        # Look for _page_DIGITS at the end or followed by more underscores
        page_pattern = r'_page_\d+$'
        base_name = re.sub(page_pattern, '', base_name)
        
        return base_name
    
    # Strategy 2: No _rip_ keyword (external software)
    # Pattern: {NAME}_{PAGE}_{COLOR}
    # Remove last two numeric parts (color and page number)
    
    parts = name.split('_')
    
    # Remove color profile (last part, single digit 0-3)
    if len(parts) >= 2 and parts[-1] in ['0', '1', '2', '3']:
        parts = parts[:-1]
    
    # Remove page number (last part, all digits)
    if len(parts) >= 2 and parts[-1].isdigit():
        parts = parts[:-1]
    
    # Also check for page_XXXX pattern in remaining parts
    result = '_'.join(parts) if parts else name
    result = re.sub(r'_page_\d+$', '', result)
    
    return result if result else name


def group_files(files: List[str]) -> Dict[str, List[str]]:
    """
    Group files by their PDF prefix.
    
    Files from the same original PDF/image will have the same prefix before "_rip_".
    Within each group, files are sorted using natural sorting.
    
    Args:
        files: List of RIP filenames (can be full paths or just filenames)
        
    Returns:
        Dict mapping group prefix to sorted list of files
        
    Example:
        >>> files = [
        ...     "Text_1_A_rip_0001_0.tif",
        ...     "Text_1_A_rip_0015_0.tif",
        ...     "Text_0_A_rip_0008_0.tif",
        ...     "Text_1_B_rip_0012_0.tif"
        ... ]
        >>> groups = group_files(files)
        >>> list(groups.keys())
        ['Text_1_A', 'Text_0_A', 'Text_1_B']
        >>> len(groups['Text_1_A'])
        2
    """
    groups = {}
    
    for file in files:
        # Extract just the filename if full path provided
        filename = Path(file).name
        prefix = extract_group_prefix(filename)
        
        if prefix not in groups:
            groups[prefix] = []
        
        groups[prefix].append(file)
    
    # Sort files within each group using natural sorting
    # This ensures page_1 comes before page_10, etc.
    for prefix in groups:
        groups[prefix].sort(key=lambda f: natural_sort_key(Path(f).name))
    
    return groups


def count_pages_in_group(files: List[str]) -> int:
    """
    Count the number of pages in a file group.
    
    Args:
        files: List of files in the group
        
    Returns:
        Number of pages (number of files)
    """
    return len(files)


def get_total_pages(groups: Dict[str, List[str]], selected_groups: List[str] = None) -> int:
    """
    Get total page count across groups.
    
    Args:
        groups: Dict mapping group prefix to list of files
        selected_groups: Optional list of group names to count (if None, counts all)
        
    Returns:
        Total number of pages
        
    Example:
        >>> groups = {
        ...     'Text_1_A': ['file1.tif', 'file2.tif'],
        ...     'Text_0_A': ['file3.tif']
        ... }
        >>> get_total_pages(groups)
        3
        >>> get_total_pages(groups, ['Text_1_A'])
        2
    """
    if selected_groups is None:
        selected_groups = list(groups.keys())
    
    total = 0
    for group_name in selected_groups:
        if group_name in groups:
            total += len(groups[group_name])
    
    return total


def flatten_selected_groups(groups: Dict[str, List[str]], selected_groups: List[str]) -> List[str]:
    """
    Flatten selected groups into a single ordered list of files.
    
    Args:
        groups: Dict mapping group prefix to list of files
        selected_groups: Ordered list of group names to include
        
    Returns:
        Flat list of files in the order of selected groups
        
    Example:
        >>> groups = {
        ...     'Text_1_A': ['a1.tif', 'a2.tif'],
        ...     'Text_0_A': ['b1.tif'],
        ...     'Text_1_B': ['c1.tif', 'c2.tif']
        ... }
        >>> flatten_selected_groups(groups, ['Text_1_B', 'Text_1_A'])
        ['c1.tif', 'c2.tif', 'a1.tif', 'a2.tif']
    """
    result = []
    for group_name in selected_groups:
        if group_name in groups:
            result.extend(groups[group_name])
    return result
