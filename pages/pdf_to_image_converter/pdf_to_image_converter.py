import fitz  # PyMuPDF for PDF handling
from pathlib import Path
import logging
import os
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
import multiprocessing
from PIL import Image

# Suppress Google API warnings about Python 3.9.12
warnings.filterwarnings('ignore', category=FutureWarning, module='google.api_core')
warnings.filterwarnings('ignore', message='.*importlib.metadata.*packages_distributions.*')

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress importlib.metadata errors in logging
import sys
_original_stderr = sys.stderr
class FilteredStderr:
    def write(self, message):
        if 'importlib.metadata' in message and 'packages_distributions' in message:
            return
        if 'FutureWarning' in message and 'google.api_core' in message:
            return
        _original_stderr.write(message)
    def flush(self):
        _original_stderr.flush()

# Only filter if not already filtered
if not isinstance(sys.stderr, FilteredStderr):
    sys.stderr = FilteredStderr()


class PDFToImageConverter:
    """Convert PDF files to images at specified DPI and rotation"""
    
    def __init__(self, output_dir="pdf_images", dpi_x=300, dpi_y=300, rotation_deg=0, max_workers=None, chunk_size=None, progress_step=None, small_pdf_threshold=None):
        """
        Initialize PDF to Image converter
        
        Args:
            output_dir: Directory to save converted images
            dpi: Resolution for image conversion (default 300)
            rotation_deg: Page rotation in degrees (0, 90, 180, 270)
        """
        self.output_dir = Path(output_dir)
        self.dpi_x = dpi_x
        self.dpi_y = dpi_y
        # Normalize rotation to allowed values
        valid_rotations = {0, 90, 180, 270, -90, -180, -270}
        self.rotation_deg = rotation_deg if rotation_deg in valid_rotations else 0
        # Worker and chunk configuration
        default_workers_cap = 32
        cpu_scaled = multiprocessing.cpu_count() * 2
        self.max_workers = max_workers if isinstance(max_workers, int) and max_workers > 0 else min(cpu_scaled, default_workers_cap)
        # Reasonable default chunk, balances process startup and memory
        self.chunk_size = chunk_size if isinstance(chunk_size, int) and chunk_size > 0 else 100
        # Progress update cadence (images per update)
        self.progress_step = progress_step if isinstance(progress_step, int) and progress_step > 0 else 100
        # Threshold under which we avoid process pool overhead and run inline
        self.small_pdf_threshold = small_pdf_threshold if isinstance(small_pdf_threshold, int) and small_pdf_threshold > 0 else 200
        
        # Optimize for speed
        os.environ['MUPDF_ACCELERATE'] = '1'
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def convert_pdf_to_images(self, pdf_path, image_format='png', rotation_deg=None, on_progress=None, on_page_done=None, cancellation_check=None, reverse_order=False):
        """
        Convert a PDF file to images
        
        Args:
            pdf_path: Path to the PDF file
            image_format: Output image format ('png', 'jpg', 'jpeg')
            rotation_deg: Optional rotation override for this conversion
            reverse_order: If True, output files are numbered in reverse (last page becomes page_0001)
            
        Returns:
            List of paths to created image files
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return []
            
        if pdf_path.suffix.lower() != '.pdf':
            logger.error(f"File is not a PDF: {pdf_path}")
            return []
            
        pdf_name = pdf_path.stem
        
        # Create subdirectory for this PDF's images
        pdf_image_dir = self.output_dir / pdf_name
        pdf_image_dir.mkdir(exist_ok=True)
        
        logger.info(f"Converting PDF: {pdf_path}")
        logger.info(f"DPI: {self.dpi_x}x{self.dpi_y}")
        rotation_to_apply = self.rotation_deg if rotation_deg is None else rotation_deg
        # Normalize rotation
        if rotation_to_apply not in {0, 90, 180, 270, -90, -180, -270}:
            rotation_to_apply = 0
        logger.info(f"Rotation: {rotation_to_apply} degrees")
        logger.info(f"Output directory: {pdf_image_dir}")
        
        image_paths = []
        
        try:
            # Open the PDF
            pdf_document = fitz.open(str(pdf_path))
            total_pages = len(pdf_document)
            
            logger.info(f"Total pages: {total_pages}")
            
            # Choose execution strategy based on size
            pdf_document.close()
            # Adaptive progress cadence: target ~5% steps, capped by configured progress_step
            progress_every = max(1, min(self.progress_step, max(1, total_pages // 20)))
            if total_pages <= self.small_pdf_threshold:
                image_paths = self._process_pages_single_process(
                    str(pdf_path),
                    total_pages,
                    pdf_name,
                    pdf_image_dir,
                    image_format,
                    rotation_to_apply,
                    on_progress=on_progress,
                    on_page_done=on_page_done,
                    cancellation_check=cancellation_check,
                    progress_every=progress_every,
                    reverse_order=reverse_order
                )
            else:
                image_paths = self._process_pages_parallel(
                    str(pdf_path),
                    total_pages,
                    pdf_name,
                    pdf_image_dir,
                    image_format,
                    rotation_to_apply,
                    on_progress=on_progress,
                    on_page_done=on_page_done,
                    cancellation_check=cancellation_check,
                    progress_every=progress_every,
                    reverse_order=reverse_order
                )
            logger.info(f"Successfully converted {total_pages} pages")
        except Exception as e:
            logger.error(f"Failed to convert PDF: {e}")
            raise
        
        return image_paths
    def _process_pages_single_process(self, pdf_path, total_pages, pdf_name, pdf_image_dir, image_format, rotation_to_apply, on_progress=None, on_page_done=None, cancellation_check=None, progress_every=1, reverse_order=False):
        """Fast path for small PDFs: render sequentially in a single process to avoid pool overhead."""
        import fitz
        from pathlib import Path
        image_paths = []
        pdf_doc = fitz.open(pdf_path)
        try:
            mat = fitz.Matrix(self.dpi_x/72.0, self.dpi_y/72.0).prerotate(rotation_to_apply)
            completed_pages = 0
            for page_num in range(total_pages):
                if cancellation_check and callable(cancellation_check):
                    try:
                        if cancellation_check():
                            break
                    except Exception:
                        pass
                try:
                    page = pdf_doc[page_num]
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    # Calculate output page number based on reverse_order flag
                    output_page_num = (total_pages - page_num) if reverse_order else (page_num + 1)
                    image_filename = f"{pdf_name}_page_{output_page_num:04d}.{image_format}"
                    image_path = Path(pdf_image_dir) / image_filename
                    PDFToImageConverter._save_pixmap_static(image_format, pix, image_path)
                    image_paths.append(str(image_path))
                    # Live per-image log
                    try:
                        logger.info(f"Finished page {page_num + 1}: {image_path}")
                    except Exception:
                        pass
                    # Callbacks
                    if on_page_done and callable(on_page_done):
                        try:
                            on_page_done(str(image_path))
                        except Exception:
                            pass
                    completed_pages += 1
                    if on_progress and callable(on_progress):
                        if (completed_pages % progress_every == 0) or (completed_pages == total_pages):
                            try:
                                on_progress(completed_pages, total_pages)
                            except Exception:
                                pass
                except Exception:
                    continue
        finally:
            pdf_doc.close()
        return image_paths
    
    def batch_convert(self, pdf_directory, recursive=False, image_format='png'):
        """
        Convert multiple PDF files in a directory
        
        Args:
            pdf_directory: Directory containing PDF files
            recursive: Process subdirectories
            image_format: Output image format
            
        Returns:
            Dictionary mapping PDF files to their image paths
        """
        pdf_dir = Path(pdf_directory)
        
        if not pdf_dir.exists():
            logger.error(f"Directory not found: {pdf_dir}")
            return {}
            
        # Find all PDF files
        if recursive:
            pdf_files = list(pdf_dir.rglob("*.pdf"))
        else:
            pdf_files = list(pdf_dir.glob("*.pdf"))
            
        if not pdf_files:
            logger.warning(f"No PDF files found in {pdf_dir}")
            return {}
            
        logger.info(f"Found {len(pdf_files)} PDF files to convert")
        
        results = {}
        
        for pdf_file in pdf_files:
            try:
                image_paths = self.convert_pdf_to_images(pdf_file, image_format)
                results[str(pdf_file)] = image_paths
            except Exception as e:
                logger.error(f"Failed to convert {pdf_file}: {e}")
                results[str(pdf_file)] = []
                
        return results

    def _process_pages_parallel(self, pdf_path, total_pages, pdf_name, pdf_image_dir, image_format, rotation_to_apply, on_progress=None, on_page_done=None, cancellation_check=None, progress_every=1, reverse_order=False):
        """Process PDF pages in parallel in chunks with progress/cancellation"""
        # Build chunk tasks as half-open ranges [start, end) with adaptive size
        # Aim roughly one chunk per worker to reduce scheduling overhead
        base_chunk = max(1, self.chunk_size)
        adaptive_chunk = max(1, (total_pages + self.max_workers - 1) // self.max_workers)
        chunk_size = max(1, min(base_chunk, adaptive_chunk))
        ranges = [(start, min(start + chunk_size, total_pages)) for start in range(0, total_pages, chunk_size)]
        logger.info(f"Processing {total_pages} pages with {self.max_workers} workers in {len(ranges)} chunks of ~{chunk_size}")

        all_image_paths = []
        completed_pages = 0
        import time
        last_emit = 0.0
        executor = ProcessPoolExecutor(max_workers=self.max_workers)
        try:
            futures = [
                executor.submit(
                    self._process_chunk,
                    (
                        pdf_path,
                        start,
                        end,
                        self.dpi_x,
                        self.dpi_y,
                        pdf_name,
                        str(pdf_image_dir),
                        image_format,
                        rotation_to_apply,
                        total_pages,
                        reverse_order,
                    ),
                ) for (start, end) in ranges
            ]

            for future in as_completed(futures):
                # Cooperative cancellation: cancel all not-yet-started tasks and stop early
                if cancellation_check and callable(cancellation_check):
                    try:
                        if cancellation_check():
                            for f in futures:
                                if not f.done():
                                    f.cancel()
                            try:
                                executor.shutdown(wait=False, cancel_futures=True)
                            except TypeError:
                                executor.shutdown(wait=False)
                            break
                    except Exception:
                        pass

                try:
                    chunk_image_paths = future.result() or []
                    all_image_paths.extend(chunk_image_paths)
                    # Progress and per-page callbacks from parent process; update every N images
                    if chunk_image_paths:
                        for img_path in chunk_image_paths:
                            if on_page_done and callable(on_page_done):
                                try:
                                    on_page_done(img_path)
                                except Exception:
                                    pass
                            completed_pages += 1
                            if on_progress and callable(on_progress):
                                now = time.time()
                                if (completed_pages % progress_every == 0) or (completed_pages == total_pages) or (now - last_emit >= 0.5):
                                    try:
                                        on_progress(completed_pages, total_pages)
                                    except Exception:
                                        pass
                                    last_emit = now
                except Exception as e:
                    logger.error(f"Chunk processing failed: {e}")
        finally:
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass

        return sorted(all_image_paths)

    @staticmethod
    def _process_chunk(args):
        """Process a contiguous chunk of pages in one process to reduce overhead.
        Returns a list of image paths for the processed pages."""
        pdf_path, start_page, end_page, dpi_x, dpi_y, pdf_name, pdf_image_dir, image_format, rotation_to_apply, total_pages, reverse_order = args
        import fitz
        from pathlib import Path

        image_paths = []
        pdf_doc = fitz.open(pdf_path)
        try:
            # Precompute transform matrix once per chunk when DPI/rotation constant
            mat = fitz.Matrix(dpi_x/72.0, dpi_y/72.0).prerotate(rotation_to_apply)
            for page_num in range(start_page, end_page):
                try:
                    page = pdf_doc[page_num]
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    # Calculate output page number based on reverse_order flag
                    output_page_num = (total_pages - page_num) if reverse_order else (page_num + 1)
                    image_filename = f"{pdf_name}_page_{output_page_num:04d}.{image_format}"
                    image_path = Path(pdf_image_dir) / image_filename
                    PDFToImageConverter._save_pixmap_static(image_format, pix, image_path)
                    image_paths.append(str(image_path))
                    # Live per-image log from child process
                    try:
                        logger.info(f"Finished page {page_num + 1}: {image_path}")
                    except Exception:
                        pass
                except Exception:
                    # Skip a failed page but continue the chunk
                    continue
        finally:
            pdf_doc.close()

        return image_paths

    @staticmethod
    def _save_pixmap_static(image_format, pix, image_path):
        """Save a PyMuPDF pixmap to disk in the requested format."""
        fmt = (image_format or "png").lower()
        path_str = str(image_path)

        try:
            if fmt in ("jpg", "jpeg"):
                pix.save(path_str, jpg_quality=85)
                return

            if fmt == "png":
                pix.save(path_str)
                return

            if fmt in ("bmp", "tif", "tiff"):
                mode = "RGB"
                if pix.n >= 4:
                    mode = "RGBA"

                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

                if fmt == "bmp":
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(path_str, format="BMP")
                else:
                    # TIFF – keep alpha if present
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGB")
                    img.save(path_str, format="TIFF")
                return

            # Fallback to PyMuPDF for any other format
            pix.save(path_str)
        except Exception as exc:
            logger.error(f"Failed to save image {path_str}: {exc}")
    
    def quick_preview_convert(self, pdf_path, preview_dpi=72):
        """Super fast preview generation at low DPI"""
        original_dpi = self.dpi
        try:
            self.dpi = preview_dpi
            return self.convert_pdf_to_images(pdf_path, image_format='jpeg')
        finally:
            self.dpi = original_dpi


def main():
    """Example usage of the PDF to Image converter"""
    
    # Configuration
    OUTPUT_DIR = "converted_images"  # Where to save images
    DPI = 300  # Resolution (300 is good for printing, 150 for screen viewing)
    
    # Create converter
    converter = PDFToImageConverter(output_dir=OUTPUT_DIR, dpi=DPI)
    
    # Example 1: Convert a single PDF
    pdf_file = "example.pdf"  # Change to your PDF file path
    if os.path.exists(pdf_file):
        images = converter.convert_pdf_to_images(pdf_file)
        print(f"Created {len(images)} images from {pdf_file}")
    
    # Example 2: Convert all PDFs in a directory
    pdf_directory = "pdfs/"  # Change to your directory path
    if os.path.exists(pdf_directory):
        results = converter.batch_convert(pdf_directory, recursive=True)
        for pdf, images in results.items():
            print(f"{pdf}: {len(images)} images created")
    
    # Example 3: Convert with different settings
    # Lower DPI for web viewing
    web_converter = PDFToImageConverter(output_dir="web_images", dpi=150)
    
    # High quality for printing
    print_converter = PDFToImageConverter(output_dir="print_images", dpi=600)
    
    # Convert to JPEG instead of PNG
    if os.path.exists(pdf_file):
        jpeg_images = converter.convert_pdf_to_images(pdf_file, image_format='jpeg')


if __name__ == "__main__":
    # Simple usage example
    import sys
    
    if len(sys.argv) > 1:
        # If PDF file is provided as command line argument
        pdf_path = sys.argv[1]
        dpi = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        
        converter = PDFToImageConverter(dpi=dpi)
        images = converter.convert_pdf_to_images(pdf_path)
        
        if images:
            print(f"Successfully converted {len(images)} pages")
            for img in images:
                print(f"  - {img}")
    else:
        print("Usage: python pdf_to_image.py <pdf_file> [dpi]")
        print("Example: python pdf_to_image.py document.pdf 300")
        print("\nRunning demo with example settings...")
        main()
