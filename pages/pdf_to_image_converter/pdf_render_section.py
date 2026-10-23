from pathlib import Path
import os
import time
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QFileDialog, QSpinBox, QMessageBox, QScrollArea, QProgressBar,
    QListWidget, QListWidgetItem, QCheckBox, QComboBox
)
from PySide6.QtGui import QPixmap, QImage, QColor

from .pdf_to_image_converter import PDFToImageConverter
from pages.images_to_rip.images_to_rip import ClientPool, ParallelImageRipProcessor


class NoScrollSpinBox(QSpinBox):
    """QSpinBox that ignores mouse wheel scroll to prevent accidental changes."""

    def wheelEvent(self, event):
        event.ignore()


class PDFConversionWorker(QObject):
    finished = Signal()
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, pdf_path, output_dir, dpi_x, dpi_y, rotation_deg, reverse_order=False, image_format="png"):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.dpi_x = dpi_x
        self.dpi_y = dpi_y
        self.rotation_deg = rotation_deg
        self.reverse_order = reverse_order
        self._cancelled = False
        self.image_format = (image_format or "png").lower()

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            pdf_path = Path(self.pdf_path)
            output_dir = Path(self.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            self.progress.emit(0, f"Opening PDF: {pdf_path.name}")

            converter = PDFToImageConverter(
                output_dir=str(output_dir),
                dpi_x=self.dpi_x,
                dpi_y=self.dpi_y,
                rotation_deg=self.rotation_deg
            )

            def on_progress(completed, total):
                pct = int(5 + (completed / total) * 95) if total else 5
                self.progress.emit(pct, f"Converting page {completed}/{total}")

            def cancellation_check():
                return self._cancelled

            image_paths = converter.convert_pdf_to_images(
                str(pdf_path),
                image_format=self.image_format,
                rotation_deg=self.rotation_deg,
                on_progress=on_progress,
                on_page_done=None,
                cancellation_check=cancellation_check,
                reverse_order=self.reverse_order
            )

            if self._cancelled:
                self.progress.emit(0, "Conversion cancelled by user")
                return

            total_images = len(image_paths)
            if total_images == 0:
                self.error.emit("No images were generated from the PDF")
                return

            self.progress.emit(100, f"Successfully converted {total_images} pages")
        except Exception as e:
            self.error.emit(f"Conversion failed: {str(e)}")
        finally:
            self.finished.emit()


class PDFToRippedWorker(QObject):
    finished = Signal()
    progress = Signal(int, str)
    error = Signal(str)
    monitor_update = Signal(int, int, float)  # connections, workers, delay

    def __init__(self, pdf_path, output_dir, dpi_x, dpi_y, rotation_deg, reverse_order=False, image_format="png", 
                 server_configs=None, distribution_mode='alternate'):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.dpi_x = dpi_x
        self.dpi_y = dpi_y
        self.rotation_deg = rotation_deg
        self.reverse_order = reverse_order
        self._cancelled = False
        self.image_format = (image_format or "png").lower()
        self.server_configs = server_configs  # List of server configs for multi-server
        self.distribution_mode = distribution_mode  # 'alternate' or 'chunks'

    def cancel(self):
        self._cancelled = True
    
    def _verify_ripped_files(self, images_dir, ripped_dir):
        """
        Verify which images don't have corresponding ripped files using fast set-based comparison.
        Returns list of image paths that failed to rip.
        """
        from pathlib import Path
        
        images_dir = Path(images_dir)
        ripped_dir = Path(ripped_dir)
        
        if not images_dir.exists():
            return []
        
        if not ripped_dir.exists():
            # No ripped directory means all failed
            return list(images_dir.rglob('*.[pP][nN][gG]')) + list(images_dir.rglob('*.[jJ][pP][gG]'))
        
        SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
        
        # Step 1: Get all image file stems (fast bulk operation)
        image_dict = {}  # stem -> full_path
        for file_path in images_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                image_dict[file_path.stem] = file_path
        
        # Step 2: Get all ripped file stems (fast bulk operation)
        # Ripped files are named: {stem}_rip_{serial}_0.bmp
        ripped_stems = set()
        for ripped_file in ripped_dir.glob('*_rip_*_0.bmp'):
            # Extract original stem by removing '_rip_{number}_0' suffix
            # Example: TEST_File_1909-001_page_6800_rip_6800_0.bmp → TEST_File_1909-001_page_6800
            stem = ripped_file.stem
            # Remove _rip_*_0 pattern from end
            if '_rip_' in stem:
                original_stem = stem.rsplit('_rip_', 1)[0]
                ripped_stems.add(original_stem)
        
        # Step 3: Set difference to find missing (ultra fast!)
        image_stems_set = set(image_dict.keys())
        missing_stems = image_stems_set - ripped_stems
        
        # Step 4: Build list of failed image paths
        failed_images = [image_dict[stem] for stem in missing_stems]
        
        return failed_images

    def run(self):
        try:
            pdf_path = Path(self.pdf_path)
            output_dir = Path(self.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Phase 1: Convert PDF to Images
            self.progress.emit(0, f"Opening PDF: {pdf_path.name}")

            converter = PDFToImageConverter(
                output_dir=str(output_dir),
                dpi_x=self.dpi_x,
                dpi_y=self.dpi_y,
                rotation_deg=self.rotation_deg
            )

            def on_progress(completed, total):
                pct = int(5 + (completed / total) * 45) if total else 5  # First 45% for PDF conversion
                self.progress.emit(pct, f"Converting page {completed}/{total}")

            def cancellation_check():
                return self._cancelled

            image_paths = converter.convert_pdf_to_images(
                str(pdf_path),
                image_format=self.image_format,
                rotation_deg=self.rotation_deg,
                on_progress=on_progress,
                on_page_done=None,
                cancellation_check=cancellation_check,
                reverse_order=self.reverse_order
            )

            if self._cancelled:
                self.progress.emit(0, "Conversion cancelled by user")
                return

            total_images = len(image_paths)
            if total_images == 0:
                self.error.emit("No images were generated from the PDF")
                return

            self.progress.emit(45, f"Successfully converted {total_images} pages to images")

            # Phase 2: RIP the generated images
            self.progress.emit(50, "Starting RIP processing...")

            # Create separate folder for RIPped images (PDF-wise) under the selected output folder
            pdf_name = Path(self.pdf_path).stem
            ripped_output_dir = output_dir / f"{pdf_name}_ripped"
            ripped_output_dir.mkdir(parents=True, exist_ok=True)

            # Configuration
            MAX_WORKERS = 12
            DELAY_BETWEEN_SUBMISSIONS = 0.2

            # Choose single-server or multi-server based on config
            if self.server_configs and len(self.server_configs) > 1:
                # Multi-server processing
                from pages.images_to_rip.images_to_rip import MultiServerClientPool, MultiServerImageRipProcessor
                
                CONNECTIONS_PER_SERVER = 4
                multi_pool = MultiServerClientPool(
                    server_configs=self.server_configs,
                    connections_per_server=CONNECTIONS_PER_SERVER
                )
                
                if not multi_pool.initialize():
                    self.error.emit("Failed to connect to one or more servers for RIP processing")
                    return
                
                processor = MultiServerImageRipProcessor(
                    multi_server_pool=multi_pool,
                    output_dir=str(ripped_output_dir),
                    max_workers=MAX_WORKERS,
                    distribution_mode=self.distribution_mode
                )
                
                total_connections = multi_pool.get_total_connections()
                server_count = multi_pool.get_server_count()
            else:
                # Single server processing (backward compatibility or single server selected)
                from pages.images_to_rip.images_to_rip import ClientPool, ParallelImageRipProcessor
                
                SERVER_HOST = self.server_configs[0]['host'] if self.server_configs else 'localhost'
                SERVER_PORT = self.server_configs[0]['port'] if self.server_configs else 2000
                NUM_CONNECTIONS = 12
                
                client_pool = ClientPool(SERVER_HOST, SERVER_PORT, pool_size=NUM_CONNECTIONS)
                if not client_pool.initialize():
                    self.error.emit("Failed to connect to Print Server for RIP processing")
                    return
                
                processor = ParallelImageRipProcessor(
                    client_pool,
                    output_dir=str(ripped_output_dir),
                    max_workers=MAX_WORKERS
                )
                
                total_connections = NUM_CONNECTIONS
                server_count = 1

            # Set cancellation callback
            processor.set_cancellation_callback(lambda: self._cancelled)

            # Monitor RIP progress and live stats
            import threading
            monitor_stop_flag = threading.Event()
            
            def monitor_rip_progress():
                last_count = 0
                while not self._cancelled and processor.processed_count < total_images and not monitor_stop_flag.is_set():
                    try:
                        current_count = processor.processed_count
                        
                        # Get live monitoring data
                        current_workers = processor.get_current_worker_count()
                        current_delay = processor.get_current_delay()
                        
                        # Only emit if worker is still valid
                        if not monitor_stop_flag.is_set():
                            self.monitor_update.emit(total_connections, current_workers, current_delay)
                        
                        if current_count != last_count:
                            # RIP progress goes from 50% to 95%
                            rip_progress = int(50 + (current_count / total_images) * 45)
                            if not monitor_stop_flag.is_set():
                                self.progress.emit(rip_progress, f"RIPped {current_count}/{total_images} images")
                            last_count = current_count
                        time.sleep(0.1)
                    except RuntimeError:
                        # Signal source deleted, stop cleanly
                        break

            monitor_thread = threading.Thread(target=monitor_rip_progress, daemon=True)
            monitor_thread.start()

            # Process only this PDF's images folder (avoid scanning entire output root)
            images_input_dir = output_dir / pdf_name
            # Fallback: if converter already wrote directly into output_dir, use it
            rip_source_dir = images_input_dir if images_input_dir.exists() else output_dir
            
            # Initial ripping attempt
            self.progress.emit(50, f"Starting RIP processing for {total_images} images...")
            success = processor.process_folder_with_cancellation(
                str(rip_source_dir),
                keep_structure=False,
                delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
                cancellation_check=lambda: self._cancelled
            )

            # Stop monitor thread cleanly before continuing
            monitor_stop_flag.set()
            monitor_thread.join(timeout=2)

            if self._cancelled:
                # Close appropriate pool
                if self.server_configs and len(self.server_configs) > 1:
                    multi_pool.close_all()
                else:
                    client_pool.close_all()
                self.progress.emit(0, "RIP processing cancelled by user")
                return

            # Verification and Retry Logic with Smart Skip
            import logging
            logger = logging.getLogger("images_to_rip")
            
            MAX_RETRIES = 3
            retry_attempt = 0
            last_retry_succeeded = False
            failed_images = []
            
            while retry_attempt < MAX_RETRIES:
                # Check which images don't have ripped files
                failed_images = self._verify_ripped_files(rip_source_dir, ripped_output_dir)
                
                if not failed_images:
                    # All images successfully ripped!
                    last_retry_succeeded = True
                    break
                
                retry_attempt += 1
                failed_count = len(failed_images)
                self.progress.emit(
                    int(50 + (retry_attempt / MAX_RETRIES) * 45),
                    f"Retry {retry_attempt}/{MAX_RETRIES}: Re-ripping {failed_count} failed images..."
                )
                
                # Log failed images
                logger.warning(f"Retry attempt {retry_attempt}: Found {failed_count} images without ripped files")
                for img in failed_images[:5]:  # Log first 5
                    logger.warning(f"  - Missing ripped file for: {img.name}")
                if failed_count > 5:
                    logger.warning(f"  ... and {failed_count - 5} more")
                
                # Small delay before retry
                time.sleep(1)
                
                # Re-process only the failed images with rotation preserved
                retry_success = processor.process_specific_images_with_cancellation(
                    failed_images,
                    rip_source_dir,
                    keep_structure=False,
                    delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
                    cancellation_check=lambda: self._cancelled,
                    rotation_deg=self.rotation_deg  # Preserve rotation for retry
                )
                
                if self._cancelled:
                    # Close appropriate pool
                    if self.server_configs and len(self.server_configs) > 1:
                        multi_pool.close_all()
                    else:
                        client_pool.close_all()
                    self.progress.emit(0, "RIP processing cancelled by user")
                    return
                
                # If retry reports success, trust it and skip final verification
                if retry_success:
                    last_retry_succeeded = True
                    logger.info(f"✅ Retry {retry_attempt} succeeded - skipping final verification for speed")
                    break
            
            # Close appropriate pool
            if self.server_configs and len(self.server_configs) > 1:
                multi_pool.close_all()
            else:
                client_pool.close_all()
            
            # Smart Skip: Only do final verification if retry didn't succeed
            if last_retry_succeeded:
                # Trust the retry result - all images are good!
                self.progress.emit(100, f"✅ All {total_images} images successfully RIPped!")
                logger.info("Skipped final verification (retry succeeded)")
            else:
                # Something's still wrong, do final verification
                logger.warning("Retry did not fully succeed, performing final verification...")
                self.progress.emit(95, "Final verification...")
                final_failed = self._verify_ripped_files(rip_source_dir, ripped_output_dir)
                
                if not final_failed:
                    self.progress.emit(100, f"✅ All {total_images} images successfully RIPped!")
                else:
                    failed_count = len(final_failed)
                    self.progress.emit(95, f"⚠️ {failed_count} images failed after {MAX_RETRIES} retries")
                    logger.error(f"Failed to RIP {failed_count} images after {MAX_RETRIES} attempts")
                    for img in final_failed:
                        logger.error(f"  - Failed: {img.name}")

        except Exception as e:
            self.error.emit(f"PDF to RIP conversion failed: {str(e)}")
        finally:
            self.finished.emit()


class ImageToRipWorker(QObject):
    """Worker for direct Image to RIP conversion (no PDF conversion phase)"""
    finished = Signal()
    progress = Signal(int, str)
    error = Signal(str)
    monitor_update = Signal(int, int, float)  # connections, workers, delay

    def __init__(self, folder_path, output_dir, rotation_deg=0, reverse_order=False, recursive=True, excluded_subfolders=None,
                 server_configs=None, distribution_mode='alternate'):
        super().__init__()
        self.folder_path = folder_path
        self.output_dir = output_dir
        self.rotation_deg = rotation_deg
        self.reverse_order = reverse_order
        self.recursive = recursive
        self.excluded_subfolders = excluded_subfolders or []
        self.server_configs = server_configs  # List of server configs for multi-server
        self.distribution_mode = distribution_mode  # 'alternate' or 'chunks'
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
    
    def _verify_ripped_files(self, images_dir, ripped_dir):
        """
        Verify which images don't have corresponding ripped files using fast set-based comparison.
        Returns list of image paths that failed to rip.
        """
        from pathlib import Path
        
        images_dir = Path(images_dir)
        ripped_dir = Path(ripped_dir)
        
        if not images_dir.exists():
            return []
        
        if not ripped_dir.exists():
            # No ripped directory means all failed
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            return [f for f in images_dir.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
        
        SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
        
        # Step 1: Get all image file stems (fast bulk operation)
        image_dict = {}  # stem -> full_path
        for file_path in images_dir.rglob('*') if self.recursive else images_dir.glob('*'):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                image_dict[file_path.stem] = file_path
        
        # Step 2: Get all ripped file stems (fast bulk operation)
        # Ripped files are named: {stem}_rip_{serial}_0.bmp
        ripped_stems = set()
        for ripped_file in ripped_dir.glob('*_rip_*_0.bmp'):
            # Extract original stem by removing '_rip_{number}_0' suffix
            stem = ripped_file.stem
            # Remove _rip_*_0 pattern from end
            if '_rip_' in stem:
                original_stem = stem.rsplit('_rip_', 1)[0]
                ripped_stems.add(original_stem)
        
        # Step 3: Set difference to find missing (ultra fast!)
        image_stems_set = set(image_dict.keys())
        missing_stems = image_stems_set - ripped_stems
        
        # Step 4: Build list of failed image paths
        failed_images = [image_dict[stem] for stem in missing_stems]
        
        return failed_images

    def run(self):
        try:
            from pathlib import Path
            import logging
            logger = logging.getLogger("images_to_rip")
            
            folder_path = Path(self.folder_path)
            output_dir = Path(self.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Scan folder structure
            self.progress.emit(0, "Scanning folder structure...")
            
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            
            # Check if there are subfolders
            all_subfolders = [d for d in folder_path.iterdir() if d.is_dir()]
            
            # Filter out excluded subfolders
            subfolders = [sf for sf in all_subfolders if str(sf) not in self.excluded_subfolders]
            
            if subfolders and self.recursive:
                # HAS SUBFOLDERS (not excluded) - Process subfolder-by-subfolder
                excluded_count = len(all_subfolders) - len(subfolders)
                if excluded_count > 0:
                    self.progress.emit(2, f"Found {len(subfolders)} subfolder(s) to process ({excluded_count} excluded)")
                else:
                    self.progress.emit(2, f"Found {len(subfolders)} subfolder(s) - processing one by one...")
                
                total_processed = 0
                total_images_count = sum([len([f for f in sf.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]) for sf in subfolders])
                
                for idx, subfolder in enumerate(subfolders):
                    if self._cancelled:
                        break
                    
                    subfolder_name = subfolder.name
                    self.progress.emit(
                        int(5 + (idx / len(subfolders)) * 90),
                        f"Processing subfolder [{idx+1}/{len(subfolders)}]: {subfolder_name}"
                    )
                    
                    # Process this subfolder
                    result = self._process_single_folder(
                        subfolder, 
                        output_dir / subfolder_name,
                        idx + 1,
                        len(subfolders),
                        total_processed
                    )
                    
                    if result:
                        total_processed += result
                
                if not self._cancelled:
                    if excluded_count > 0:
                        self.progress.emit(100, f"✅ {len(subfolders)} subfolders processed! ({total_processed} images, {excluded_count} excluded)")
                        QTimer.singleShot(100, lambda: QMessageBox.information(
                            None, "Conversion Complete", 
                            f"Successfully processed {len(subfolders)} subfolder(s)!\n{total_processed} total images converted to RIP format!\n({excluded_count} subfolder(s) excluded)"
                        ))
                    else:
                        self.progress.emit(100, f"✅ All {len(subfolders)} subfolders processed! ({total_processed} images total)")
                        QTimer.singleShot(100, lambda: QMessageBox.information(
                            None, "Conversion Complete", 
                            f"Successfully processed {len(subfolders)} subfolder(s)!\n{total_processed} total images converted to RIP format!"
                        ))
            else:
                # NO SUBFOLDERS - Process all images at once (like PDF to RIPPED)
                if self.recursive:
                    image_files = [f for f in folder_path.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
                else:
                    image_files = [f for f in folder_path.glob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
                
                if not image_files:
                    self.error.emit("No images found in the selected folder")
                    return
                
                self.progress.emit(5, f"Found {len(image_files)} images (no subfolders)")
                
                # Process all images at once
                result = self._process_single_folder(folder_path, output_dir, 1, 1, 0)
                
                if not self._cancelled and result:
                    self.progress.emit(100, f"✅ All {result} images successfully RIPped!")
                    QTimer.singleShot(100, lambda: QMessageBox.information(
                        None, "Conversion Complete", 
                        f"Successfully converted {result} images to RIP format!"
                    ))

        except Exception as e:
            self.error.emit(f"Image to RIP conversion failed: {str(e)}")
        finally:
            self.finished.emit()
    
    def _process_single_folder(self, source_folder, dest_folder, folder_idx, total_folders, images_processed_so_far):
        """Process a single folder (subfolder or main folder) with retry logic"""
        from pathlib import Path
        import logging
        import threading
        logger = logging.getLogger("images_to_rip")
        
        source_folder = Path(source_folder)
        dest_folder = Path(dest_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
        
        # Collect images from this folder
        if self.recursive and source_folder != Path(self.folder_path):
            # It's a subfolder, get all images recursively
            image_files = [f for f in source_folder.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
        else:
            # Main folder or non-recursive
            image_files = [f for f in source_folder.glob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
        
        if not image_files:
            logger.warning(f"No images in folder: {source_folder.name}")
            return 0
        
        # Sort and optionally reverse
        image_files.sort()
        if self.reverse_order:
            image_files.reverse()
        
        total_images = len(image_files)
        folder_name = source_folder.name if source_folder != Path(self.folder_path) else "main folder"
        
        # Configuration
        MAX_WORKERS = 12
        DELAY_BETWEEN_SUBMISSIONS = 0.2

        # Choose single-server or multi-server based on config
        if self.server_configs and len(self.server_configs) > 1:
            # Multi-server processing
            from pages.images_to_rip.images_to_rip import MultiServerClientPool, MultiServerImageRipProcessor
            
            CONNECTIONS_PER_SERVER = 4
            multi_pool = MultiServerClientPool(
                server_configs=self.server_configs,
                connections_per_server=CONNECTIONS_PER_SERVER
            )
            
            if not multi_pool.initialize():
                self.error.emit(f"Failed to connect to one or more servers for {folder_name}")
                return 0
            
            processor = MultiServerImageRipProcessor(
                multi_server_pool=multi_pool,
                output_dir=str(dest_folder),
                max_workers=MAX_WORKERS,
                distribution_mode=self.distribution_mode
            )
            
            total_connections = multi_pool.get_total_connections()
            server_count = multi_pool.get_server_count()
        else:
            # Single server processing (backward compatibility or single server selected)
            from pages.images_to_rip.images_to_rip import ClientPool, ParallelImageRipProcessor
            
            if self.server_configs and len(self.server_configs) == 1:
                # Use selected server
                SERVER_HOST = self.server_configs[0]['host']
                SERVER_PORT = self.server_configs[0]['port']
            else:
                # Fallback to default (backward compatibility)
                SERVER_HOST = 'localhost'
                SERVER_PORT = 2000
            
            NUM_CONNECTIONS = 12
            client_pool = ClientPool(SERVER_HOST, SERVER_PORT, pool_size=NUM_CONNECTIONS)
            if not client_pool.initialize():
                self.error.emit(f"Failed to connect to Print Server for {folder_name}")
                return 0
            
            processor = ParallelImageRipProcessor(
                client_pool,
                output_dir=str(dest_folder),
                max_workers=MAX_WORKERS
            )
            
            total_connections = NUM_CONNECTIONS
            server_count = 1

        processor.set_cancellation_callback(lambda: self._cancelled)

        # Monitor progress
        monitor_stop_flag = threading.Event()
        
        def monitor_rip_progress():
            last_count = 0
            while not self._cancelled and processor.processed_count < total_images and not monitor_stop_flag.is_set():
                try:
                    current_count = processor.processed_count
                    current_workers = processor.get_current_worker_count()
                    current_delay = processor.get_current_delay()
                    
                    if not monitor_stop_flag.is_set():
                        self.monitor_update.emit(total_connections, current_workers, current_delay)
                    
                    if current_count != last_count:
                        msg = f"[{folder_idx}/{total_folders}] {folder_name}: {current_count}/{total_images} images"
                        if not monitor_stop_flag.is_set():
                            self.progress.emit(int(10 + (current_count / total_images) * 70), msg)
                        last_count = current_count
                    time.sleep(0.1)
                except RuntimeError:
                    # Signal source deleted, stop cleanly
                    break

        monitor_thread = threading.Thread(target=monitor_rip_progress, daemon=True)
        monitor_thread.start()

        # Process images
        success = processor.process_folder_with_cancellation(
            str(source_folder),
            keep_structure=False,
            delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
            cancellation_check=lambda: self._cancelled,
            rotation_deg=self.rotation_deg  # Apply rotation during initial processing
        )

        # Stop monitor thread cleanly before continuing
        monitor_stop_flag.set()
        monitor_thread.join(timeout=2)

        if self._cancelled:
            if self.server_configs and len(self.server_configs) > 1:
                multi_pool.close_all()
            else:
                client_pool.close_all()
            return 0

        # Verification and Retry Logic
        MAX_RETRIES = 3
        retry_attempt = 0
        last_retry_succeeded = False
        
        while retry_attempt < MAX_RETRIES:
            failed_images = self._verify_ripped_files(source_folder, dest_folder)
            
            if not failed_images:
                last_retry_succeeded = True
                break
            
            retry_attempt += 1
            failed_count = len(failed_images)
            self.progress.emit(
                int(80 + (retry_attempt / MAX_RETRIES) * 15),
                f"[{folder_idx}/{total_folders}] Retry {retry_attempt}/{MAX_RETRIES}: {failed_count} images"
            )
            
            logger.warning(f"{folder_name} - Retry {retry_attempt}: {failed_count} failed images")
            
            time.sleep(1)
            
            retry_success = processor.process_specific_images_with_cancellation(
                failed_images,
                source_folder,
                keep_structure=False,
                delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
                cancellation_check=lambda: self._cancelled,
                rotation_deg=self.rotation_deg  # Preserve rotation for retry
            )
            
            if self._cancelled:
                if self.server_configs and len(self.server_configs) > 1:
                    multi_pool.close_all()
                else:
                    client_pool.close_all()
                return 0
            
            if retry_success:
                last_retry_succeeded = True
                logger.info(f"✅ {folder_name} - Retry {retry_attempt} succeeded")
                break
        
        # Close appropriate pool
        if self.server_configs and len(self.server_configs) > 1:
            multi_pool.close_all()
        else:
            client_pool.close_all()
        
        if last_retry_succeeded:
            logger.info(f"✅ {folder_name} completed: {total_images} images")
            return total_images
        else:
            final_failed = self._verify_ripped_files(source_folder, dest_folder)
            if not final_failed:
                return total_images
            else:
                logger.error(f"❌ {folder_name} failed: {len(final_failed)} images")
                return total_images - len(final_failed)


class PDFRenderSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._render_preview)
        
        self._ripped_preview_timer = QTimer(self)
        self._ripped_preview_timer.setSingleShot(True)
        self._ripped_preview_timer.timeout.connect(self._render_ripped_preview)
        self._init_ui()
        
        # Queue management
        self._pdf_queue = []
        self._current_pdf_index = -1
        self._cancel_requested = False

    def _style_group_box(self, group_box):
        try:
            group_box.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    font-size: 12pt;
                    color: #212529;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    margin-top: 20px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0 8px;
                    background: transparent;
                    font-weight: bold;
                    font-size: 12pt;
                    color: #000000;
                }
            """)
        except Exception:
            pass

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        self.initial_buttons_container = self._create_initial_buttons()
        self.to_image_container = self._create_pdf_to_image_ui()
        self.to_ripped_container = self._create_pdf_to_ripped_ui()
        self.image_to_rip_container = self._create_image_to_rip_ui()

        main_layout.addWidget(self.initial_buttons_container)
        main_layout.addWidget(self.to_image_container)
        main_layout.addWidget(self.to_ripped_container)
        main_layout.addWidget(self.image_to_rip_container)
        self._show_initial()

    def _show_initial(self):
        self.initial_buttons_container.setVisible(True)
        self.to_image_container.setVisible(False)
        self.to_ripped_container.setVisible(False)
        self.image_to_rip_container.setVisible(False)

    def _show_to_image(self):
        self.initial_buttons_container.setVisible(False)
        self.to_image_container.setVisible(True)
        self.to_ripped_container.setVisible(False)
        self.image_to_rip_container.setVisible(False)

    def _show_to_ripped(self):
        self.initial_buttons_container.setVisible(False)
        self.to_image_container.setVisible(False)
        self.to_ripped_container.setVisible(True)
        self.image_to_rip_container.setVisible(False)

    def _show_image_to_rip(self):
        self.initial_buttons_container.setVisible(False)
        self.to_image_container.setVisible(False)
        self.to_ripped_container.setVisible(False)
        self.image_to_rip_container.setVisible(True)

    def _create_initial_buttons(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addStretch(2)
        row = QHBoxLayout()
        row.addStretch()

        btn_img = QPushButton("PDF to IMAGE")
        btn_img.setMinimumSize(200, 80)
        btn_img.setStyleSheet("""
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
        """)
        btn_img.clicked.connect(self._show_to_image)
        row.addWidget(btn_img)

        row.addSpacing(40)

        btn_rip = QPushButton("PDF to RIP (GIS)")
        btn_rip.setMinimumSize(200, 80)
        btn_rip.setStyleSheet("""
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
        """)
        btn_rip.clicked.connect(self._show_to_ripped)
        row.addWidget(btn_rip)

        row.addSpacing(40)

        btn_img_to_rip = QPushButton("IMAGE to RIP")
        btn_img_to_rip.setMinimumSize(200, 80)
        btn_img_to_rip.setStyleSheet("""
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
        """)
        btn_img_to_rip.clicked.connect(self._show_image_to_rip)
        row.addWidget(btn_img_to_rip)

        row.addStretch()
        layout.addLayout(row)
        layout.addStretch(3)
        return container

    def _create_pdf_to_ripped_ui(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        
        back_btn = QPushButton("\u2190 Back to Main Menu")
        back_btn.setMaximumWidth(200)
        back_btn.clicked.connect(self._show_initial)
        outer_layout.addWidget(back_btn)
        
        container = QWidget()
        layout = QHBoxLayout(container)

        # Left controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)

        # FOLDER selection instead of file
        folder_group = QGroupBox("Input Folder")
        self._style_group_box(folder_group)
        folder_layout = QVBoxLayout()
        self.ripped_folder_path_edit = QLineEdit()
        self.ripped_folder_path_edit.setPlaceholderText("Select folder containing PDFs...")
        self.ripped_folder_path_edit.setReadOnly(True)
        ripped_folder_browse_btn = QPushButton("Browse Folder")
        ripped_folder_browse_btn.clicked.connect(self._select_ripped_folder)
        folder_layout.addWidget(self.ripped_folder_path_edit)
        folder_layout.addWidget(ripped_folder_browse_btn)
        folder_group.setLayout(folder_layout)
        controls_layout.addWidget(folder_group)
        
        # Output Folder selection
        output_group = QGroupBox("Output Folder")
        self._style_group_box(output_group)
        output_layout = QVBoxLayout()
        self.ripped_output_folder_edit = QLineEdit()
        self.ripped_output_folder_edit.setPlaceholderText("Select base output folder (subfolders per PDF will be created)...")
        self.ripped_output_folder_edit.setReadOnly(True)
        ripped_output_browse_btn = QPushButton("Browse Output Folder")
        ripped_output_browse_btn.clicked.connect(self._select_ripped_output_folder)
        output_layout.addWidget(self.ripped_output_folder_edit)
        output_layout.addWidget(ripped_output_browse_btn)
        output_group.setLayout(output_layout)
        controls_layout.addWidget(output_group)

        # Server Selection group
        server_select_group = QGroupBox("🖥️ GIS Server Selection")
        self._style_group_box(server_select_group)
        server_select_layout = QVBoxLayout()
        
        # Load servers from config
        from pages.multi_server_print.server_manager import PrintServerManager
        self.pdf_rip_server_manager = PrintServerManager()
        
        # Server list with checkboxes
        self.pdf_rip_server_list = QListWidget()
        self.pdf_rip_server_list.setMaximumHeight(120)
        self.pdf_rip_server_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
        """)
        self._load_pdf_rip_servers()
        server_select_layout.addWidget(QLabel("Select servers for RIP processing:"))
        server_select_layout.addWidget(self.pdf_rip_server_list)
        
        # Distribution mode
        dist_layout = QHBoxLayout()
        dist_layout.addWidget(QLabel("Distribution:"))
        self.pdf_rip_distribution_combo = QComboBox()
        self.pdf_rip_distribution_combo.addItems(["Alternate (Round-Robin)", "Chunks"])
        self.pdf_rip_distribution_combo.setCurrentIndex(0)  # Default to Alternate
        dist_layout.addWidget(self.pdf_rip_distribution_combo)
        server_select_layout.addLayout(dist_layout)
        
        # Refresh button
        pdf_refresh_btn = QPushButton("🔄 Refresh Servers")
        pdf_refresh_btn.clicked.connect(self._refresh_pdf_rip_servers)
        pdf_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        server_select_layout.addWidget(pdf_refresh_btn)
        
        server_select_group.setLayout(server_select_layout)
        controls_layout.addWidget(server_select_group)

        # PDF List with checkboxes
        list_group = QGroupBox("PDFs to Process")
        self._style_group_box(list_group)
        list_layout = QVBoxLayout()
        self.ripped_pdf_list_widget = QListWidget()
        self.ripped_pdf_list_widget.setMinimumHeight(150)
        self.ripped_pdf_list_widget.itemSelectionChanged.connect(self._on_ripped_pdf_selected)
        list_layout.addWidget(self.ripped_pdf_list_widget)
        list_group.setLayout(list_layout)
        controls_layout.addWidget(list_group)

        # Output format selection for RIP workflow
        format_group = QGroupBox("Output Image Format")
        self._style_group_box(format_group)
        format_layout = QVBoxLayout()
        self.ripped_format_combo = QComboBox()
        self.ripped_format_combo.addItem("PNG (.png)", "png")
        self.ripped_format_combo.addItem("JPEG (.jpeg)", "jpeg")
        self.ripped_format_combo.addItem("TIFF (.tif)", "tif")
        self.ripped_format_combo.addItem("Bitmap (.bmp)", "bmp")
        self.ripped_format_combo.setCurrentIndex(0)
        format_layout.addWidget(self.ripped_format_combo)
        format_group.setLayout(format_layout)
        controls_layout.addWidget(format_group)

        # DPI Settings - Separate X and Y
        dpi_group = QGroupBox("DPI Settings")
        self._style_group_box(dpi_group)
        dpi_layout = QVBoxLayout()

        x_dpi_row = QHBoxLayout()
        x_dpi_row.addWidget(QLabel("X Resolution (DPI):"))
        self.ripped_dpi_x_spin = NoScrollSpinBox()
        self.ripped_dpi_x_spin.setRange(72, 1200)
        self.ripped_dpi_x_spin.setValue(360)
        self.ripped_dpi_x_spin.valueChanged.connect(self._update_ripped_pdf_preview)
        x_dpi_row.addWidget(self.ripped_dpi_x_spin)
        dpi_layout.addLayout(x_dpi_row)

        y_dpi_row = QHBoxLayout()
        y_dpi_row.addWidget(QLabel("Y Resolution (DPI):"))
        self.ripped_dpi_y_spin = NoScrollSpinBox()
        self.ripped_dpi_y_spin.setRange(72, 1200)
        self.ripped_dpi_y_spin.setValue(360)
        self.ripped_dpi_y_spin.valueChanged.connect(self._update_ripped_pdf_preview)
        y_dpi_row.addWidget(self.ripped_dpi_y_spin)
        dpi_layout.addLayout(y_dpi_row)

        dpi_group.setLayout(dpi_layout)
        controls_layout.addWidget(dpi_group)

        # Rotation
        rot_group = QGroupBox("Page Rotation")
        self._style_group_box(rot_group)
        rot_layout = QVBoxLayout()
        from PySide6.QtWidgets import QRadioButton, QButtonGroup
        self.ripped_rotation_buttons = QButtonGroup(self)
        self.ripped_rot_0 = QRadioButton("0° (No rotation)")
        self.ripped_rot_90 = QRadioButton("90° (Clockwise)")
        self.ripped_rot_180 = QRadioButton("180° (Upside down)")
        self.ripped_rot_270 = QRadioButton("270° (Counter-clockwise)")
        self.ripped_rot_0.setChecked(True)
        for i, btn in enumerate([self.ripped_rot_0, self.ripped_rot_90, self.ripped_rot_180, self.ripped_rot_270]):
            rot_layout.addWidget(btn)
            self.ripped_rotation_buttons.addButton(btn, [0, 90, 180, 270][i])
        rot_group.setLayout(rot_layout)
        self.ripped_rotation_buttons.buttonToggled.connect(lambda *_: self._update_ripped_pdf_preview())
        controls_layout.addWidget(rot_group)

        # Reverse Order option
        reverse_group = QGroupBox("Page Order")
        self._style_group_box(reverse_group)
        reverse_layout = QVBoxLayout()
        self.ripped_reverse_order_checkbox = QCheckBox("Reverse Order (Last page becomes first)")
        self.ripped_reverse_order_checkbox.setChecked(False)
        self.ripped_reverse_order_checkbox.setToolTip("Output files will be numbered in reverse: last page gets page_0001, first page gets the last number")
        reverse_layout.addWidget(self.ripped_reverse_order_checkbox)
        reverse_group.setLayout(reverse_layout)
        controls_layout.addWidget(reverse_group)

        # Progress
        progress_group = QGroupBox("Conversion Progress")
        self._style_group_box(progress_group)
        pg_layout = QVBoxLayout()
        self.ripped_progress_bar = QProgressBar()
        self.ripped_progress_bar.setVisible(False)
        self.ripped_progress_bar.setStyleSheet("QProgressBar { color: #000000; font-weight: bold; }")
        self.ripped_progress_status_label = QLabel("Ready to convert")
        self.ripped_progress_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        pg_layout.addWidget(self.ripped_progress_bar)
        pg_layout.addWidget(self.ripped_progress_status_label)
        progress_group.setLayout(pg_layout)
        controls_layout.addWidget(progress_group)

        # Live Monitoring
        monitor_group = QGroupBox("Live Processing Monitor")
        self._style_group_box(monitor_group)
        monitor_layout = QVBoxLayout()
        
        # Connections (fixed)
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Connections:"))
        self.ripped_connections_label = QLabel("--")
        self.ripped_connections_label.setStyleSheet("color: #0066cc; font-weight: bold; font-size: 11pt;")
        conn_layout.addWidget(self.ripped_connections_label)
        conn_layout.addStretch()
        monitor_layout.addLayout(conn_layout)
        
        # Workers (adaptive)
        workers_layout = QHBoxLayout()
        workers_layout.addWidget(QLabel("Workers:"))
        self.ripped_workers_label = QLabel("--")
        self.ripped_workers_label.setStyleSheet("color: #00aa00; font-weight: bold; font-size: 11pt;")
        workers_layout.addWidget(self.ripped_workers_label)
        workers_layout.addStretch()
        monitor_layout.addLayout(workers_layout)
        
        # Delay (adaptive)
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("Delay:"))
        self.ripped_delay_label = QLabel("--")
        self.ripped_delay_label.setStyleSheet("color: #ff6600; font-weight: bold; font-size: 11pt;")
        delay_layout.addWidget(self.ripped_delay_label)
        delay_layout.addStretch()
        monitor_layout.addLayout(delay_layout)
        
        monitor_group.setLayout(monitor_layout)
        controls_layout.addWidget(monitor_group)

        # Actions
        actions_group = QGroupBox("Actions")
        self._style_group_box(actions_group)
        actions_layout = QVBoxLayout()
        self.start_ripped_conversion_btn = QPushButton("Start PDF to RIP Conversion")
        self.start_ripped_conversion_btn.clicked.connect(self._start_ripped_batch_conversion)
        self.stop_ripped_conversion_btn = QPushButton("STOP")
        self.stop_ripped_conversion_btn.setObjectName("StopButton")
        self.stop_ripped_conversion_btn.clicked.connect(self._stop_ripped_conversion)
        self.stop_ripped_conversion_btn.setEnabled(False)
        self.open_ripped_output_btn = QPushButton("Open Output Folder")
        self.open_ripped_output_btn.clicked.connect(self._open_ripped_output_folder)
        actions_layout.addWidget(self.start_ripped_conversion_btn)
        actions_layout.addWidget(self.stop_ripped_conversion_btn)
        actions_layout.addWidget(self.open_ripped_output_btn)
        actions_group.setLayout(actions_layout)
        controls_layout.addWidget(actions_group)

        controls_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(controls_widget)
        left_scroll.setMinimumWidth(320)
        layout.addWidget(left_scroll, 0)

        # Right preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_group = QGroupBox("PDF Preview (First Page)")
        self._style_group_box(preview_group)
        preview_content_layout = QVBoxLayout()
        self.ripped_preview_label = QLabel("No PDF selected")
        self.ripped_preview_label.setAlignment(Qt.AlignCenter)
        self.ripped_preview_label.setStyleSheet("border: 1px solid #dee2e6; background-color: #f8f9fa; padding: 20px;")
        self.ripped_preview_scroll = QScrollArea()
        self.ripped_preview_scroll.setWidgetResizable(True)
        self.ripped_preview_scroll.setWidget(self.ripped_preview_label)
        self.ripped_preview_scroll.setMinimumHeight(400)
        preview_content_layout.addWidget(self.ripped_preview_scroll)
        preview_group.setLayout(preview_content_layout)
        preview_layout.addWidget(preview_group)

        layout.addWidget(preview_widget, 1)
        layout.setStretch(0, 3)
        layout.setStretch(1, 7)

        self.ripped_pdf_output_dir = None
        self.ripped_output_folder_edit.setPlaceholderText("No output folder selected - please browse to select")

        outer_layout.addWidget(container, 1)
        return outer

    def _create_pdf_to_image_ui(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        
        back_btn = QPushButton("\u2190 Back to Main Menu")
        back_btn.setMaximumWidth(200)
        back_btn.clicked.connect(self._show_initial)
        outer_layout.addWidget(back_btn)
        
        container = QWidget()
        layout = QHBoxLayout(container)

        # Left controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)

        # FOLDER selection instead of file
        folder_group = QGroupBox("Input Folder")
        self._style_group_box(folder_group)
        folder_layout = QVBoxLayout()
        self.folder_path_edit = QLineEdit()
        self.folder_path_edit.setPlaceholderText("Select folder containing PDFs...")
        self.folder_path_edit.setReadOnly(True)
        folder_browse_btn = QPushButton("Browse Folder")
        folder_browse_btn.clicked.connect(self._select_folder)
        folder_layout.addWidget(self.folder_path_edit)
        folder_layout.addWidget(folder_browse_btn)
        folder_group.setLayout(folder_layout)
        controls_layout.addWidget(folder_group)
        
        # Output Folder selection
        output_group = QGroupBox("Output Folder")
        self._style_group_box(output_group)
        output_layout = QVBoxLayout()
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Select base output folder (subfolders per PDF will be created)...")
        self.output_folder_edit.setReadOnly(True)
        output_browse_btn = QPushButton("Browse Output Folder")
        output_browse_btn.clicked.connect(self._select_output_folder)
        output_layout.addWidget(self.output_folder_edit)
        output_layout.addWidget(output_browse_btn)
        output_group.setLayout(output_layout)
        controls_layout.addWidget(output_group)

        # PDF List with checkboxes
        list_group = QGroupBox("PDFs to Process")
        self._style_group_box(list_group)
        list_layout = QVBoxLayout()
        self.pdf_list_widget = QListWidget()
        self.pdf_list_widget.setMinimumHeight(150)
        self.pdf_list_widget.itemSelectionChanged.connect(self._on_pdf_selected)
        list_layout.addWidget(self.pdf_list_widget)
        list_group.setLayout(list_layout)
        controls_layout.addWidget(list_group)

        # Output format selection
        format_group = QGroupBox("Output Image Format")
        self._style_group_box(format_group)
        format_layout = QVBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG (.png)", "png")
        self.format_combo.addItem("JPEG (.jpeg)", "jpeg")
        self.format_combo.addItem("TIFF (.tif)", "tif")
        self.format_combo.addItem("Bitmap (.bmp)", "bmp")
        self.format_combo.setCurrentIndex(0)
        format_layout.addWidget(self.format_combo)
        format_group.setLayout(format_layout)
        controls_layout.addWidget(format_group)

        # DPI Settings - Separate X and Y
        dpi_group = QGroupBox("DPI Settings")
        self._style_group_box(dpi_group)
        dpi_layout = QVBoxLayout()

        x_dpi_row = QHBoxLayout()
        x_dpi_row.addWidget(QLabel("X Resolution (DPI):"))
        self.dpi_x_spin = NoScrollSpinBox()
        self.dpi_x_spin.setRange(72, 1200)
        self.dpi_x_spin.setValue(360)
        self.dpi_x_spin.valueChanged.connect(self._update_pdf_preview)
        x_dpi_row.addWidget(self.dpi_x_spin)
        dpi_layout.addLayout(x_dpi_row)

        y_dpi_row = QHBoxLayout()
        y_dpi_row.addWidget(QLabel("Y Resolution (DPI):"))
        self.dpi_y_spin = NoScrollSpinBox()
        self.dpi_y_spin.setRange(72, 1200)
        self.dpi_y_spin.setValue(360)
        self.dpi_y_spin.valueChanged.connect(self._update_pdf_preview)
        y_dpi_row.addWidget(self.dpi_y_spin)
        dpi_layout.addLayout(y_dpi_row)

        dpi_group.setLayout(dpi_layout)
        controls_layout.addWidget(dpi_group)

        # Rotation
        rot_group = QGroupBox("Page Rotation")
        self._style_group_box(rot_group)
        rot_layout = QVBoxLayout()
        from PySide6.QtWidgets import QRadioButton, QButtonGroup
        self.rotation_buttons = QButtonGroup(self)
        self.rot_0 = QRadioButton("0° (No rotation)")
        self.rot_90 = QRadioButton("90° (Clockwise)")
        self.rot_180 = QRadioButton("180° (Upside down)")
        self.rot_270 = QRadioButton("270° (Counter-clockwise)")
        self.rot_0.setChecked(True)
        for i, btn in enumerate([self.rot_0, self.rot_90, self.rot_180, self.rot_270]):
            rot_layout.addWidget(btn)
            self.rotation_buttons.addButton(btn, [0, 90, 180, 270][i])
        rot_group.setLayout(rot_layout)
        self.rotation_buttons.buttonToggled.connect(lambda *_: self._update_pdf_preview())
        controls_layout.addWidget(rot_group)

        # Reverse Order option
        reverse_group = QGroupBox("Page Order")
        self._style_group_box(reverse_group)
        reverse_layout = QVBoxLayout()
        self.reverse_order_checkbox = QCheckBox("Reverse Order (Last page becomes first)")
        self.reverse_order_checkbox.setChecked(False)
        self.reverse_order_checkbox.setToolTip("Output files will be numbered in reverse: last page gets page_0001, first page gets the last number")
        reverse_layout.addWidget(self.reverse_order_checkbox)
        reverse_group.setLayout(reverse_layout)
        controls_layout.addWidget(reverse_group)

        # Progress
        progress_group = QGroupBox("Conversion Progress")
        self._style_group_box(progress_group)
        pg_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { color: #000000; font-weight: bold; }")
        self.progress_status_label = QLabel("Ready to convert")
        self.progress_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        pg_layout.addWidget(self.progress_bar)
        pg_layout.addWidget(self.progress_status_label)
        progress_group.setLayout(pg_layout)
        controls_layout.addWidget(progress_group)

        # Actions
        actions_group = QGroupBox("Actions")
        self._style_group_box(actions_group)
        actions_layout = QVBoxLayout()
        self.start_conversion_btn = QPushButton("Start Conversion")
        self.start_conversion_btn.clicked.connect(self._start_batch_conversion)
        self.stop_conversion_btn = QPushButton("STOP")
        self.stop_conversion_btn.setObjectName("StopButton")
        self.stop_conversion_btn.clicked.connect(self._stop_conversion)
        self.stop_conversion_btn.setEnabled(False)
        self.open_output_btn = QPushButton("Open Output Folder")
        self.open_output_btn.clicked.connect(self._open_output_folder)
        actions_layout.addWidget(self.start_conversion_btn)
        actions_layout.addWidget(self.stop_conversion_btn)
        actions_layout.addWidget(self.open_output_btn)
        actions_group.setLayout(actions_layout)
        controls_layout.addWidget(actions_group)

        controls_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(controls_widget)
        left_scroll.setMinimumWidth(320)
        layout.addWidget(left_scroll, 0)

        # Right preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_group = QGroupBox("PDF Preview (First Page)")
        self._style_group_box(preview_group)
        preview_content_layout = QVBoxLayout()
        self.preview_label = QLabel("No PDF selected")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid #dee2e6; background-color: #f8f9fa; padding: 20px;")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setMinimumHeight(400)
        preview_content_layout.addWidget(self.preview_scroll)
        preview_group.setLayout(preview_content_layout)
        preview_layout.addWidget(preview_group)

        layout.addWidget(preview_widget, 1)
        layout.setStretch(0, 3)
        layout.setStretch(1, 7)

        self.pdf_output_dir = None
        self.output_folder_edit.setPlaceholderText("No output folder selected - please browse to select")

        outer_layout.addWidget(container, 1)
        return outer

    def _get_selected_rotation(self) -> int:
        checked = self.rotation_buttons.checkedId()
        return checked if checked != -1 else 0

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with PDFs", os.getcwd())
        if folder:
            self.folder_path_edit.setText(folder)
            self._load_pdfs_from_folder(folder)

    def _select_output_folder(self):
        start_dir = str(self.pdf_output_dir) if self.pdf_output_dir else os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
        if folder:
            self.pdf_output_dir = Path(folder)
            try:
                self.pdf_output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self.output_folder_edit.setText(str(self.pdf_output_dir))

    def _load_pdfs_from_folder(self, folder_path: str):
        self.pdf_list_widget.clear()
        self._pdf_items = []
        
        try:
            p = Path(folder_path)
            pdf_files = sorted(p.glob("*.pdf"))
            
            for pdf_file in pdf_files:
                item = QListWidgetItem()
                widget = QWidget()
                hl = QHBoxLayout(widget)
                hl.setContentsMargins(4, 2, 4, 2)
                
                name_lbl = QLabel(pdf_file.name)
                name_lbl.setStyleSheet("font-weight: 600;")
                
                exclude_btn = QPushButton("✖")
                exclude_btn.setToolTip("Exclude from processing")
                exclude_btn.setFixedWidth(28)
                exclude_btn.setStyleSheet(
                    "QPushButton{background:#dc3545; color:white; font-weight:700; border:none; border-radius:4px;} "
                    "QPushButton:hover{background:#b02a37;}"
                )
                
                hl.addWidget(name_lbl, 1)
                hl.addWidget(exclude_btn, 0)
                widget.setLayout(hl)
                
                item.setSizeHint(widget.sizeHint())
                self.pdf_list_widget.addItem(item)
                self.pdf_list_widget.setItemWidget(item, widget)
                
                record = {
                    "path": str(pdf_file),
                    "name": pdf_file.name,
                    "excluded": False,
                    "item": item,
                    "label": name_lbl
                }
                self._pdf_items.append(record)
                
                # Closure to capture current record
                def make_toggle(rec):
                    def toggle():
                        rec["excluded"] = not rec["excluded"]
                        if rec["excluded"]:
                            rec["label"].setStyleSheet("text-decoration: line-through; color:#dc3545; font-weight:600;")
                        else:
                            rec["label"].setStyleSheet("font-weight: 600;")
                    return toggle
                
                exclude_btn.clicked.connect(make_toggle(record))
            
            if self.pdf_list_widget.count() > 0:
                self.pdf_list_widget.setCurrentRow(0)
                self._on_pdf_selected()
                
        except Exception as e:
            QMessageBox.warning(self, "Load PDFs", f"Failed to load PDFs: {e}")

    def _on_pdf_selected(self):
        current_row = self.pdf_list_widget.currentRow()
        if 0 <= current_row < len(self._pdf_items):
            self._current_preview_path = self._pdf_items[current_row]["path"]
            self._update_pdf_preview()

    def _update_pdf_preview(self):
        pdf_path = getattr(self, '_current_preview_path', None)
        if not pdf_path or not os.path.exists(pdf_path):
            self.preview_label.setText("No PDF selected")
            return
        
        if self._preview_timer.isActive():
            self._preview_timer.stop()
        self._preview_timer.start(150)

    def _render_preview(self):
        pdf_path = getattr(self, '_current_preview_path', None)
        if not pdf_path or not os.path.exists(pdf_path):
            return
        
        try:
            import fitz
            preview_dpi_x = min(self.dpi_x_spin.value(), 144)
            preview_dpi_y = min(self.dpi_y_spin.value(), 144)
            rotation = self._get_selected_rotation()
            
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                self.preview_label.setText("Empty PDF")
                doc.close()
                return
            
            page = doc[0]
            mat = fitz.Matrix(preview_dpi_x/72.0, preview_dpi_y/72.0).prerotate(rotation)
            pix = page.get_pixmap(matrix=mat)
            
            if pix.alpha:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
            else:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            
            qimg = qimg.copy()
            pixmap = QPixmap.fromImage(qimg)
            
            max_w = self.preview_scroll.width() - 40
            max_h = self.preview_scroll.height() - 40
            if max_w > 0 and max_h > 0:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.preview_label.setPixmap(pixmap)
            doc.close()
        except Exception as e:
            self.preview_label.setText(f"Preview error: {e}")

    def _start_batch_conversion(self):
        if not hasattr(self, '_pdf_items') or not self._pdf_items:
            QMessageBox.warning(self, "No PDFs", "Please select a folder with PDF files first.")
            return
        
        if self.pdf_output_dir is None:
            QMessageBox.warning(self, "No Output Folder", "Please select an output folder first.")
            return
        
        # Build queue of non-excluded PDFs
        self._pdf_queue = [item["path"] for item in self._pdf_items if not item["excluded"]]
        
        if not self._pdf_queue:
            QMessageBox.warning(self, "No PDFs Selected", "All PDFs are excluded. Please include at least one.")
            return
        
        self._current_pdf_index = -1
        self._cancel_requested = False
        
        self.start_conversion_btn.setEnabled(False)
        self.stop_conversion_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Start processing first PDF
        self._process_next_pdf()

    def _process_next_pdf(self):
        if self._cancel_requested:
            self._finish_batch(cancelled=True)
            return
        
        self._current_pdf_index += 1
        
        if self._current_pdf_index >= len(self._pdf_queue):
            self._finish_batch(cancelled=False)
            return
        
        current_pdf_path = self._pdf_queue[self._current_pdf_index]
        pdf_name = Path(current_pdf_path).stem
        
        # Create per-PDF output folder
        per_pdf_output = self.pdf_output_dir / pdf_name
        per_pdf_output.mkdir(parents=True, exist_ok=True)
        
        self.progress_status_label.setText(
            f"Processing PDF {self._current_pdf_index + 1}/{len(self._pdf_queue)}: {pdf_name}"
        )
        
        # Determine output format
        image_format = "png"
        if hasattr(self, "format_combo") and self.format_combo is not None:
            selected = self.format_combo.currentData()
            if selected:
                image_format = selected

        # Create fresh thread and worker
        self.conversion_thread = QThread()
        self.conversion_worker = PDFConversionWorker(
             current_pdf_path,
             str(self.pdf_output_dir),
             self.dpi_x_spin.value(),
             self.dpi_y_spin.value(),
             self._get_selected_rotation(),
             reverse_order=self.reverse_order_checkbox.isChecked(),
             image_format=image_format
         )
        self.conversion_worker.moveToThread(self.conversion_thread)
        
        # Connect signals
        self.conversion_thread.started.connect(self.conversion_worker.run)
        self.conversion_worker.finished.connect(self.conversion_thread.quit)
        self.conversion_worker.finished.connect(self.conversion_worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)
        self.conversion_worker.progress.connect(self._update_conversion_progress)
        self.conversion_worker.error.connect(self._handle_conversion_error)

        # IMPORTANT: Chain to the next PDF only after QThread has fully finished,
        # not merely when the worker emits finished. This prevents the next
        # thread from starting while the previous thread object is still alive.
        self.conversion_thread.finished.connect(self._process_next_pdf)
        
        self.conversion_thread.start()

    def _stop_conversion(self):
        self._cancel_requested = True
        if hasattr(self, 'conversion_worker') and self.conversion_worker:
            self.conversion_worker.cancel()
        self.progress_status_label.setText("Stopping...")
        self.stop_conversion_btn.setEnabled(False)

    def _finish_batch(self, cancelled=False):
        self.start_conversion_btn.setEnabled(True)
        self.stop_conversion_btn.setEnabled(False)
        
        if cancelled:
            self.progress_status_label.setText("Conversion cancelled")
        else:
            self.progress_bar.setVisible(False)
            self.progress_status_label.setText(f"All {len(self._pdf_queue)} PDFs converted successfully!")
            
            # Delay the message box to avoid blocking thread cleanup
            QTimer.singleShot(100, lambda: QMessageBox.information(
                self, "Batch Complete", 
                f"Successfully converted {len(self._pdf_queue)} PDFs!"
            ))
        # Ensure no lingering worker thread remains (best-effort)
        try:
            if hasattr(self, 'conversion_thread') and self.conversion_thread is not None:
                # If still running, request quit and wait briefly
                if self.conversion_thread.isRunning():
                    self.conversion_thread.quit()
                    self.conversion_thread.wait(1000)
        except Exception:
            pass

    def _update_conversion_progress(self, percentage, message):
        self.progress_bar.setValue(percentage)
        # Show which PDF we're on
        pdf_info = f"[{self._current_pdf_index + 1}/{len(self._pdf_queue)}] {message}"
        self.progress_status_label.setText(pdf_info)

    def _handle_conversion_error(self, error_message):
        self.progress_status_label.setText(f"Error: {error_message}")
        QMessageBox.critical(self, "Conversion Error", error_message)

    def _open_output_folder(self):
        try:
            path = str(self.pdf_output_dir.resolve())
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                os.system(f"xdg-open '{path}'")
            else:
                os.system(f"open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open folder: {e}")

    # --- Ripped Section Handler Methods ---
    def _get_ripped_selected_rotation(self) -> int:
        checked = self.ripped_rotation_buttons.checkedId()
        return checked if checked != -1 else 0

    def _load_pdf_rip_servers(self):
        """Load servers from config and populate list with checkboxes"""
        self.pdf_rip_server_list.clear()
        servers = self.pdf_rip_server_manager.get_all_servers()
        
        for server_id, config in servers.items():
            if not config.enabled:
                continue  # Skip disabled servers
            
            item = QListWidgetItem()
            from PySide6.QtWidgets import QCheckBox
            checkbox = QCheckBox(f"{config.name} ({config.ip}:{config.port})")
            checkbox.setChecked(True)  # Default to checked
            checkbox.setProperty("server_id", server_id)
            checkbox.setProperty("server_config", config)
            
            self.pdf_rip_server_list.addItem(item)
            self.pdf_rip_server_list.setItemWidget(item, checkbox)
        
        if self.pdf_rip_server_list.count() == 0:
            item = QListWidgetItem("⚠️ No servers configured. Go to GIS SERVER CONFIG.")
            self.pdf_rip_server_list.addItem(item)
    
    def _refresh_pdf_rip_servers(self):
        """Refresh server list from configuration file"""
        from pages.multi_server_print.server_manager import PrintServerManager
        self.pdf_rip_server_manager = PrintServerManager()  # Reload from file
        self._load_pdf_rip_servers()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Servers Refreshed", "Server list has been refreshed from configuration.")
    
    def _get_selected_pdf_rip_servers(self):
        """Get list of selected server configurations"""
        selected_servers = []
        
        for i in range(self.pdf_rip_server_list.count()):
            item = self.pdf_rip_server_list.item(i)
            widget = self.pdf_rip_server_list.itemWidget(item)
            
            from PySide6.QtWidgets import QCheckBox
            if isinstance(widget, QCheckBox) and widget.isChecked():
                server_id = widget.property("server_id")
                config = widget.property("server_config")
                
                if server_id and config:
                    selected_servers.append({
                        'id': server_id,
                        'host': config.ip,
                        'port': config.port,
                        'name': config.name
                    })
        
        return selected_servers

    def _select_ripped_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with PDFs", os.getcwd())
        if folder:
            self.ripped_folder_path_edit.setText(folder)
            self._load_ripped_pdfs_from_folder(folder)

    def _select_ripped_output_folder(self):
        start_dir = str(self.ripped_pdf_output_dir) if self.ripped_pdf_output_dir else os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
        if folder:
            self.ripped_pdf_output_dir = Path(folder)
            try:
                self.ripped_pdf_output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self.ripped_output_folder_edit.setText(str(self.ripped_pdf_output_dir))

    def _load_ripped_pdfs_from_folder(self, folder_path: str):
        self.ripped_pdf_list_widget.clear()
        self._ripped_pdf_items = []
        
        try:
            p = Path(folder_path)
            pdf_files = sorted(p.glob("*.pdf"))
            
            for pdf_file in pdf_files:
                item = QListWidgetItem()
                widget = QWidget()
                hl = QHBoxLayout(widget)
                hl.setContentsMargins(4, 2, 4, 2)
                
                name_lbl = QLabel(pdf_file.name)
                name_lbl.setStyleSheet("font-weight: 600;")
                
                exclude_btn = QPushButton("✖")
                exclude_btn.setToolTip("Exclude from processing")
                exclude_btn.setFixedWidth(28)
                exclude_btn.setStyleSheet(
                    "QPushButton{background:#dc3545; color:white; font-weight:700; border:none; border-radius:4px;} "
                    "QPushButton:hover{background:#b02a37;}"
                )
                
                hl.addWidget(name_lbl, 1)
                hl.addWidget(exclude_btn, 0)
                widget.setLayout(hl)
                
                item.setSizeHint(widget.sizeHint())
                self.ripped_pdf_list_widget.addItem(item)
                self.ripped_pdf_list_widget.setItemWidget(item, widget)
                
                record = {
                    "path": str(pdf_file),
                    "name": pdf_file.name,
                    "excluded": False,
                    "item": item,
                    "label": name_lbl
                }
                self._ripped_pdf_items.append(record)
                
                # Closure to capture current record
                def make_toggle(rec):
                    def toggle():
                        rec["excluded"] = not rec["excluded"]
                        if rec["excluded"]:
                            rec["label"].setStyleSheet("text-decoration: line-through; color:#dc3545; font-weight:600;")
                        else:
                            rec["label"].setStyleSheet("font-weight: 600;")
                    return toggle
                
                exclude_btn.clicked.connect(make_toggle(record))
            
            if self.ripped_pdf_list_widget.count() > 0:
                self.ripped_pdf_list_widget.setCurrentRow(0)
                self._on_ripped_pdf_selected()
                
        except Exception as e:
            QMessageBox.warning(self, "Load PDFs", f"Failed to load PDFs: {e}")

    def _on_ripped_pdf_selected(self):
        current_row = self.ripped_pdf_list_widget.currentRow()
        if 0 <= current_row < len(self._ripped_pdf_items):
            self._ripped_current_preview_path = self._ripped_pdf_items[current_row]["path"]
            self._update_ripped_pdf_preview()

    def _update_ripped_pdf_preview(self):
        pdf_path = getattr(self, '_ripped_current_preview_path', None)
        if not pdf_path or not os.path.exists(pdf_path):
            self.ripped_preview_label.setText("No PDF selected")
            return
        
        if self._ripped_preview_timer.isActive():
            self._ripped_preview_timer.stop()
        self._ripped_preview_timer.start(150)

    def _render_ripped_preview(self):
        pdf_path = getattr(self, '_ripped_current_preview_path', None)
        if not pdf_path or not os.path.exists(pdf_path):
            return
        
        try:
            import fitz
            preview_dpi_x = min(self.ripped_dpi_x_spin.value(), 144)
            preview_dpi_y = min(self.ripped_dpi_y_spin.value(), 144)
            rotation = self._get_ripped_selected_rotation()
            
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                self.ripped_preview_label.setText("Empty PDF")
                doc.close()
                return
            
            page = doc[0]
            mat = fitz.Matrix(preview_dpi_x/72.0, preview_dpi_y/72.0).prerotate(rotation)
            pix = page.get_pixmap(matrix=mat)
            
            if pix.alpha:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
            else:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            
            qimg = qimg.copy()
            pixmap = QPixmap.fromImage(qimg)
            
            max_w = self.ripped_preview_scroll.width() - 40
            max_h = self.ripped_preview_scroll.height() - 40
            if max_w > 0 and max_h > 0:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.ripped_preview_label.setPixmap(pixmap)
            doc.close()
        except Exception as e:
            self.ripped_preview_label.setText(f"Preview error: {e}")

    def _start_ripped_batch_conversion(self):
        if not hasattr(self, '_ripped_pdf_items') or not self._ripped_pdf_items:
            QMessageBox.warning(self, "No PDFs", "Please select a folder with PDF files first.")
            return
        
        if self.ripped_pdf_output_dir is None:
            QMessageBox.warning(self, "No Output Folder", "Please select an output folder first.")
            return
        
        # Build queue of non-excluded PDFs
        self._ripped_pdf_queue = [item["path"] for item in self._ripped_pdf_items if not item["excluded"]]
        
        if not self._ripped_pdf_queue:
            QMessageBox.warning(self, "No PDFs Selected", "All PDFs are excluded. Please include at least one.")
            return
        
        self._ripped_current_pdf_index = -1
        self._ripped_cancel_requested = False
        
        self.start_ripped_conversion_btn.setEnabled(False)
        self.stop_ripped_conversion_btn.setEnabled(True)
        self.ripped_progress_bar.setVisible(True)
        self.ripped_progress_bar.setValue(0)
        
        # Initialize monitor display
        self.ripped_connections_label.setText("12")
        self.ripped_workers_label.setText("12")
        self.ripped_delay_label.setText("0.200s")
        
        # Start processing first PDF
        self._process_next_ripped_pdf()

    def _process_next_ripped_pdf(self):
        if self._ripped_cancel_requested:
            self._finish_ripped_batch(cancelled=True)
            return
        
        self._ripped_current_pdf_index += 1
        
        if self._ripped_current_pdf_index >= len(self._ripped_pdf_queue):
            self._finish_ripped_batch(cancelled=False)
            return
        
        current_pdf_path = self._ripped_pdf_queue[self._ripped_current_pdf_index]
        pdf_name = Path(current_pdf_path).stem
        
        # Create per-PDF output folder
        per_pdf_output = self.ripped_pdf_output_dir / pdf_name
        per_pdf_output.mkdir(parents=True, exist_ok=True)
        
        self.ripped_progress_status_label.setText(
            f"Processing PDF {self._ripped_current_pdf_index + 1}/{len(self._ripped_pdf_queue)}: {pdf_name}"
        )
        
        # Determine output format
        ripped_image_format = "png"
        if hasattr(self, "ripped_format_combo") and self.ripped_format_combo is not None:
            selected = self.ripped_format_combo.currentData()
            if selected:
                ripped_image_format = selected

        # Create fresh thread and worker
        self.ripped_conversion_thread = QThread()
        # Get selected servers and distribution mode
        selected_servers = self._get_selected_pdf_rip_servers()
        distribution_mode = 'alternate' if self.pdf_rip_distribution_combo.currentIndex() == 0 else 'chunks'
        
        self.ripped_conversion_worker = PDFToRippedWorker(
             current_pdf_path,
             str(self.ripped_pdf_output_dir),
             self.ripped_dpi_x_spin.value(),
             self.ripped_dpi_y_spin.value(),
             self._get_ripped_selected_rotation(),
             reverse_order=self.ripped_reverse_order_checkbox.isChecked(),
             image_format=ripped_image_format,
             server_configs=selected_servers if selected_servers else None,
             distribution_mode=distribution_mode
         )
        self.ripped_conversion_worker.moveToThread(self.ripped_conversion_thread)
        
        # Connect signals
        self.ripped_conversion_thread.started.connect(self.ripped_conversion_worker.run)
        self.ripped_conversion_worker.finished.connect(self.ripped_conversion_thread.quit)
        self.ripped_conversion_worker.finished.connect(self.ripped_conversion_worker.deleteLater)
        self.ripped_conversion_thread.finished.connect(self.ripped_conversion_thread.deleteLater)
        self.ripped_conversion_worker.progress.connect(self._update_ripped_conversion_progress)
        self.ripped_conversion_worker.error.connect(self._handle_ripped_conversion_error)
        self.ripped_conversion_worker.monitor_update.connect(self._update_ripped_monitor)

        # Chain to the next PDF
        self.ripped_conversion_thread.finished.connect(self._process_next_ripped_pdf)
        
        self.ripped_conversion_thread.start()

    def _stop_ripped_conversion(self):
        self._ripped_cancel_requested = True
        if hasattr(self, 'ripped_conversion_worker') and self.ripped_conversion_worker:
            self.ripped_conversion_worker.cancel()
        self.ripped_progress_status_label.setText("Stopping...")
        self.stop_ripped_conversion_btn.setEnabled(False)

    def _finish_ripped_batch(self, cancelled=False):
        self.start_ripped_conversion_btn.setEnabled(True)
        self.stop_ripped_conversion_btn.setEnabled(False)
        
        # Reset monitor display
        self.ripped_connections_label.setText("--")
        self.ripped_workers_label.setText("--")
        self.ripped_delay_label.setText("--")
        
        if cancelled:
            self.ripped_progress_status_label.setText("Conversion cancelled")
        else:
            self.ripped_progress_bar.setVisible(False)
            self.ripped_progress_status_label.setText(f"All {len(self._ripped_pdf_queue)} PDFs converted and RIPped successfully!")
            
            # Delay the message box to avoid blocking thread cleanup
            QTimer.singleShot(100, lambda: QMessageBox.information(
                self, "Batch Complete", 
                f"Successfully converted and RIPped {len(self._ripped_pdf_queue)} PDFs!"
            ))
        # Ensure no lingering worker thread remains (best-effort)
        try:
            if hasattr(self, 'ripped_conversion_thread') and self.ripped_conversion_thread is not None:
                # If still running, request quit and wait briefly
                if self.ripped_conversion_thread.isRunning():
                    self.ripped_conversion_thread.quit()
                    self.ripped_conversion_thread.wait(1000)
        except Exception:
            pass

    def _update_ripped_conversion_progress(self, percentage, message):
        self.ripped_progress_bar.setValue(percentage)
        # Show which PDF we're on
        pdf_info = f"[{self._ripped_current_pdf_index + 1}/{len(self._ripped_pdf_queue)}] {message}"
        self.ripped_progress_status_label.setText(pdf_info)
    
    def _update_ripped_monitor(self, connections, workers, delay):
        """Update live monitoring display with current processing stats"""
        self.ripped_connections_label.setText(f"{connections}")
        self.ripped_workers_label.setText(f"{workers}")
        self.ripped_delay_label.setText(f"{delay:.3f}s")

    def _handle_ripped_conversion_error(self, error_message):
        self.ripped_progress_status_label.setText(f"Error: {error_message}")
        QMessageBox.critical(self, "Conversion Error", error_message)

    def _open_ripped_output_folder(self):
        try:
            path = str(self.ripped_pdf_output_dir.resolve())
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                os.system(f"xdg-open '{path}'")
            else:
                os.system(f"open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open folder: {e}")

    # --- IMAGE to RIP Handler Methods ---
    def _get_img_rip_selected_rotation(self) -> int:
        checked = self.img_rip_rotation_buttons.checkedId()
        return checked if checked != -1 else 0

    def _on_img_rip_rotation_changed(self):
        """Update preview when rotation selection changes"""
        # Only update if we have a folder selected and images
        folder_path = self.img_rip_folder_path_edit.text().strip()
        if folder_path and os.path.exists(folder_path):
            self._update_img_rip_count()  # This will refresh the preview with new rotation

    def _load_img_rip_servers(self):
        """Load servers from config and populate IMAGE to RIP list with checkboxes"""
        self.img_rip_server_list.clear()
        servers = self.img_rip_server_manager.get_all_servers()
        
        for server_id, config in servers.items():
            if not config.enabled:
                continue  # Skip disabled servers
            
            item = QListWidgetItem()
            from PySide6.QtWidgets import QCheckBox
            checkbox = QCheckBox(f"{config.name} ({config.ip}:{config.port})")
            checkbox.setChecked(True)  # Default to checked
            checkbox.setProperty("server_id", server_id)
            checkbox.setProperty("server_config", config)
            
            self.img_rip_server_list.addItem(item)
            self.img_rip_server_list.setItemWidget(item, checkbox)
        
        if self.img_rip_server_list.count() == 0:
            item = QListWidgetItem("⚠️ No servers configured. Go to GIS SERVER CONFIG.")
            self.img_rip_server_list.addItem(item)
    
    def _refresh_img_rip_servers(self):
        """Refresh IMAGE to RIP server list from configuration file"""
        from pages.multi_server_print.server_manager import PrintServerManager
        self.img_rip_server_manager = PrintServerManager()  # Reload from file
        self._load_img_rip_servers()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Servers Refreshed", "Server list has been refreshed from configuration.")
    
    def _get_selected_img_rip_servers(self):
        """Get list of selected server configurations for IMAGE to RIP"""
        selected_servers = []
        
        for i in range(self.img_rip_server_list.count()):
            item = self.img_rip_server_list.item(i)
            widget = self.img_rip_server_list.itemWidget(item)
            
            from PySide6.QtWidgets import QCheckBox
            if isinstance(widget, QCheckBox) and widget.isChecked():
                server_id = widget.property("server_id")
                config = widget.property("server_config")
                
                if server_id and config:
                    selected_servers.append({
                        'id': server_id,
                        'host': config.ip,
                        'port': config.port,
                        'name': config.name
                    })
        
        return selected_servers

    def _select_img_rip_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with Images", os.getcwd())
        if folder:
            self.img_rip_folder_path_edit.setText(folder)
            self._update_img_rip_count()

    def _select_img_rip_output_folder(self):
        start_dir = str(self.img_rip_output_dir) if self.img_rip_output_dir else os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
        if folder:
            self.img_rip_output_dir = Path(folder)
            try:
                self.img_rip_output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self.img_rip_output_folder_edit.setText(str(self.img_rip_output_dir))

    def _update_img_rip_count(self):
        folder_path = self.img_rip_folder_path_edit.text().strip()
        if not folder_path or not os.path.exists(folder_path):
            self.img_rip_folder_summary_label.setText("No folder selected")
            self.img_rip_subfolder_list_widget.clear()
            self.img_rip_preview_label.setText("No folder selected\n\nSelect a folder to preview an image")
            return
        
        self._load_subfolders_from_folder(folder_path)
    
    def _load_subfolders_from_folder(self, folder_path: str):
        """Load subfolders into list widget with exclude buttons (like PDF list)"""
        self.img_rip_subfolder_list_widget.clear()
        self._img_rip_subfolder_items = []
        
        try:
            from pathlib import Path
            p = Path(folder_path)
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            
            # Get subfolders
            subfolders = sorted([d for d in p.iterdir() if d.is_dir()])
            subfolder_count = len(subfolders)
            
            # Count images based on checkbox
            if self.img_rip_recursive_checkbox.isChecked():
                # All images including subfolders
                image_files = [f for f in p.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
                image_count = len(image_files)
                
                if subfolder_count > 0:
                    # Has subfolders - show in list
                    self.img_rip_folder_summary_label.setText(f"📁 {subfolder_count} subfolder(s) • 📷 {image_count} image(s) total")
                    self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #28a745; padding: 5px;")
                    
                    # Populate subfolder list
                    for subfolder in subfolders:
                        # Count images in this subfolder
                        subfolder_images = [f for f in subfolder.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
                        subfolder_image_count = len(subfolder_images)
                        
                        item = QListWidgetItem()
                        widget = QWidget()
                        hl = QHBoxLayout(widget)
                        hl.setContentsMargins(4, 2, 4, 2)
                        
                        name_lbl = QLabel(f"📁 {subfolder.name} ({subfolder_image_count} images)")
                        name_lbl.setStyleSheet("font-weight: 600;")
                        
                        exclude_btn = QPushButton("✖")
                        exclude_btn.setToolTip("Exclude from processing")
                        exclude_btn.setFixedWidth(28)
                        exclude_btn.setStyleSheet(
                            "QPushButton{background:#dc3545; color:white; font-weight:700; border:none; border-radius:4px;} "
                            "QPushButton:hover{background:#b02a37;}"
                        )
                        
                        hl.addWidget(name_lbl, 1)
                        hl.addWidget(exclude_btn, 0)
                        widget.setLayout(hl)
                        
                        item.setSizeHint(widget.sizeHint())
                        self.img_rip_subfolder_list_widget.addItem(item)
                        self.img_rip_subfolder_list_widget.setItemWidget(item, widget)
                        
                        record = {
                            "path": str(subfolder),
                            "name": subfolder.name,
                            "excluded": False,
                            "item": item,
                            "label": name_lbl,
                            "image_count": subfolder_image_count
                        }
                        self._img_rip_subfolder_items.append(record)
                        
                        # Closure to capture current record
                        def make_toggle(rec):
                            def toggle():
                                rec["excluded"] = not rec["excluded"]
                                if rec["excluded"]:
                                    rec["label"].setStyleSheet("text-decoration: line-through; color:#dc3545; font-weight:600;")
                                else:
                                    rec["label"].setStyleSheet("font-weight: 600;")
                                # Update summary count
                                self._update_subfolder_summary()
                            return toggle
                        
                        exclude_btn.clicked.connect(make_toggle(record))
                else:
                    # No subfolders
                    self.img_rip_folder_summary_label.setText(f"📷 {image_count} image(s) found (no subfolders)")
                    self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #28a745; padding: 5px;")
            else:
                # Only top-level images
                image_files = [f for f in p.glob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
                image_count = len(image_files)
                
                if subfolder_count > 0:
                    self.img_rip_folder_summary_label.setText(f"📷 {image_count} image(s) in main folder (🚫 subfolders excluded)")
                    self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ff6600; padding: 5px;")
                    # Still show subfolders but grayed out
                    for subfolder in subfolders:
                        item = QListWidgetItem(f"🚫 {subfolder.name} (excluded)")
                        item.setForeground(QColor("#6c757d"))
                        self.img_rip_subfolder_list_widget.addItem(item)
                else:
                    self.img_rip_folder_summary_label.setText(f"📷 {image_count} image(s) found")
                    self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #28a745; padding: 5px;")
            
            # Update preview with first image
            self._update_img_rip_preview(image_files)
            
        except Exception as e:
            self.img_rip_folder_summary_label.setText(f"Error: {e}")
            self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #dc3545; padding: 5px;")
            self.img_rip_preview_label.setText(f"Error loading preview:\n{e}")
    
    def _update_subfolder_summary(self):
        """Update summary label based on excluded subfolders"""
        if not hasattr(self, '_img_rip_subfolder_items'):
            return
        
        total = len(self._img_rip_subfolder_items)
        excluded = sum(1 for item in self._img_rip_subfolder_items if item["excluded"])
        included = total - excluded
        
        total_images = sum(item["image_count"] for item in self._img_rip_subfolder_items if not item["excluded"])
        
        if included == 0:
            self.img_rip_folder_summary_label.setText(f"⚠️ All {total} subfolders excluded!")
            self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #dc3545; padding: 5px;")
        elif excluded > 0:
            self.img_rip_folder_summary_label.setText(f"📁 {included}/{total} subfolder(s) • 📷 {total_images} image(s) ({excluded} excluded)")
            self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ff6600; padding: 5px;")
        else:
            self.img_rip_folder_summary_label.setText(f"📁 {total} subfolder(s) • 📷 {total_images} image(s) total")
            self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #28a745; padding: 5px;")

    def _update_img_rip_preview(self, image_files):
        """Show preview of first image from the list with rotation applied"""
        if not image_files:
            self.img_rip_preview_label.setText("No images found in selected folder")
            return
        
        try:
            # Get first image for preview
            first_image = image_files[0]
            
            # Load and display image
            pixmap = QPixmap(str(first_image))
            if pixmap.isNull():
                self.img_rip_preview_label.setText(f"Could not load image:\n{first_image.name}")
                return
            
            # Apply rotation if selected
            rotation_deg = self._get_img_rip_selected_rotation()
            if rotation_deg != 0:
                # Apply rotation using QTransform
                from PySide6.QtGui import QTransform
                transform = QTransform()
                transform.rotate(rotation_deg)
                pixmap = pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Scale to fit preview area
            max_w = self.img_rip_preview_scroll.width() - 40
            max_h = self.img_rip_preview_scroll.height() - 40
            if max_w > 0 and max_h > 0:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.img_rip_preview_label.setPixmap(pixmap)
            self.img_rip_preview_label.setText("")  # Clear text when showing image
            
        except Exception as e:
            self.img_rip_preview_label.setText(f"Preview error:\n{str(e)}")

    def _start_img_rip_conversion(self):
        folder_path = self.img_rip_folder_path_edit.text().strip()
        if not folder_path or not os.path.exists(folder_path):
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid input folder containing images.")
            return
        
        if self.img_rip_output_dir is None:
            QMessageBox.warning(self, "No Output Folder", "Please select an output folder first.")
            return
        
        # Check if there are images
        from pathlib import Path
        p = Path(folder_path)
        SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
        
        if self.img_rip_recursive_checkbox.isChecked():
            image_files = [f for f in p.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
        else:
            image_files = [f for f in p.glob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
        
        if not image_files:
            QMessageBox.warning(self, "No Images", "No supported images found in the selected folder.")
            return
        
        # Get excluded subfolder paths
        excluded_subfolder_paths = []
        if hasattr(self, '_img_rip_subfolder_items'):
            excluded_subfolder_paths = [item["path"] for item in self._img_rip_subfolder_items if item["excluded"]]
            
            # Check if all subfolders are excluded
            if len(self._img_rip_subfolder_items) > 0:
                included_count = sum(1 for item in self._img_rip_subfolder_items if not item["excluded"])
                if included_count == 0:
                    QMessageBox.warning(self, "All Excluded", "All subfolders are excluded! Please include at least one subfolder.")
                    return
        
        # Disable controls
        self.start_img_rip_conversion_btn.setEnabled(False)
        self.stop_img_rip_conversion_btn.setEnabled(True)
        self.img_rip_progress_bar.setVisible(True)
        self.img_rip_progress_bar.setValue(0)
        
        # Initialize monitor display
        self.img_rip_connections_label.setText("12")
        self.img_rip_workers_label.setText("12")
        self.img_rip_delay_label.setText("0.200s")
        
        self._img_rip_cancel_requested = False
        
        # Get selected servers and distribution mode
        server_configs = self._get_selected_img_rip_servers()
        
        if not server_configs:
            QMessageBox.warning(self, "No Server Selected", 
                              "Please select at least one GIS server from the list.\n"
                              "If no servers are available, configure them in GIS SERVER CONFIG section.")
            self.start_img_rip_conversion_btn.setEnabled(True)
            self.stop_img_rip_conversion_btn.setEnabled(False)
            return
        
        distribution_text = self.img_rip_distribution_combo.currentText()
        distribution_mode = 'alternate' if 'Alternate' in distribution_text else 'chunks'
        
        # Create thread and worker
        self.img_rip_conversion_thread = QThread()
        self.img_rip_conversion_worker = ImageToRipWorker(
            folder_path,
            str(self.img_rip_output_dir),
            self._get_img_rip_selected_rotation(),
            reverse_order=self.img_rip_reverse_order_checkbox.isChecked(),
            recursive=self.img_rip_recursive_checkbox.isChecked(),
            excluded_subfolders=excluded_subfolder_paths,  # Pass excluded subfolders!
            server_configs=server_configs,  # Pass selected servers
            distribution_mode=distribution_mode  # Pass distribution mode
        )
        self.img_rip_conversion_worker.moveToThread(self.img_rip_conversion_thread)
        
        # Connect signals
        self.img_rip_conversion_thread.started.connect(self.img_rip_conversion_worker.run)
        self.img_rip_conversion_worker.finished.connect(self.img_rip_conversion_thread.quit)
        self.img_rip_conversion_worker.finished.connect(self.img_rip_conversion_worker.deleteLater)
        self.img_rip_conversion_thread.finished.connect(self.img_rip_conversion_thread.deleteLater)
        self.img_rip_conversion_worker.progress.connect(self._update_img_rip_conversion_progress)
        self.img_rip_conversion_worker.error.connect(self._handle_img_rip_conversion_error)
        self.img_rip_conversion_worker.monitor_update.connect(self._update_img_rip_monitor)
        self.img_rip_conversion_worker.finished.connect(self._finish_img_rip_conversion)
        
        self.img_rip_conversion_thread.start()

    def _stop_img_rip_conversion(self):
        self._img_rip_cancel_requested = True
        if hasattr(self, 'img_rip_conversion_worker') and self.img_rip_conversion_worker:
            self.img_rip_conversion_worker.cancel()
        self.img_rip_progress_status_label.setText("Stopping...")
        self.stop_img_rip_conversion_btn.setEnabled(False)

    def _finish_img_rip_conversion(self):
        self.start_img_rip_conversion_btn.setEnabled(True)
        self.stop_img_rip_conversion_btn.setEnabled(False)
        
        # Reset monitor display
        self.img_rip_connections_label.setText("--")
        self.img_rip_workers_label.setText("--")
        self.img_rip_delay_label.setText("--")
        
        if self._img_rip_cancel_requested:
            self.img_rip_progress_status_label.setText("Conversion cancelled")
        else:
            self.img_rip_progress_bar.setVisible(False)
            # Success message will be set by worker

    def _update_img_rip_conversion_progress(self, percentage, message):
        self.img_rip_progress_bar.setValue(percentage)
        self.img_rip_progress_status_label.setText(message)
    
    def _update_img_rip_monitor(self, connections, workers, delay):
        """Update live monitoring display with current processing stats"""
        self.img_rip_connections_label.setText(f"{connections}")
        self.img_rip_workers_label.setText(f"{workers}")
        self.img_rip_delay_label.setText(f"{delay:.3f}s")

    def _handle_img_rip_conversion_error(self, error_message):
        self.img_rip_progress_status_label.setText(f"Error: {error_message}")
        QMessageBox.critical(self, "Conversion Error", error_message)

    def _open_img_rip_output_folder(self):
        try:
            path = str(self.img_rip_output_dir.resolve())
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                os.system(f"xdg-open '{path}'")
            else:
                os.system(f"open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open folder: {e}")

    def _create_image_to_rip_ui(self):
        """Create UI for direct Image to RIP conversion (no PDF, no DPI)"""
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        
        back_btn = QPushButton("← Back to Main Menu")
        back_btn.setMaximumWidth(200)
        back_btn.clicked.connect(self._show_initial)
        outer_layout.addWidget(back_btn)
        
        container = QWidget()
        layout = QHBoxLayout(container)

        # Left controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)

        # Input Folder selection
        folder_group = QGroupBox("Input Folder (Images)")
        self._style_group_box(folder_group)
        folder_layout = QVBoxLayout()
        self.img_rip_folder_path_edit = QLineEdit()
        self.img_rip_folder_path_edit.setPlaceholderText("Select folder containing images...")
        self.img_rip_folder_path_edit.setReadOnly(True)
        img_rip_folder_browse_btn = QPushButton("Browse Image Folder")
        img_rip_folder_browse_btn.clicked.connect(self._select_img_rip_folder)
        folder_layout.addWidget(self.img_rip_folder_path_edit)
        folder_layout.addWidget(img_rip_folder_browse_btn)
        
        # Include Subdirectories option (moved here - right below folder selection)
        self.img_rip_recursive_checkbox = QCheckBox("Include Subdirectories (Recursive)")
        self.img_rip_recursive_checkbox.setChecked(True)
        self.img_rip_recursive_checkbox.setToolTip("Process images in all subdirectories")
        self.img_rip_recursive_checkbox.toggled.connect(self._update_img_rip_count)
        folder_layout.addWidget(self.img_rip_recursive_checkbox)
        
        folder_group.setLayout(folder_layout)
        controls_layout.addWidget(folder_group)
        
        # Output Folder selection
        output_group = QGroupBox("Output Folder (RIP Files)")
        self._style_group_box(output_group)
        output_layout = QVBoxLayout()
        self.img_rip_output_folder_edit = QLineEdit()
        self.img_rip_output_folder_edit.setPlaceholderText("Select output folder for RIP files...")
        self.img_rip_output_folder_edit.setReadOnly(True)
        img_rip_output_browse_btn = QPushButton("Browse Output Folder")
        img_rip_output_browse_btn.clicked.connect(self._select_img_rip_output_folder)
        output_layout.addWidget(self.img_rip_output_folder_edit)
        output_layout.addWidget(img_rip_output_browse_btn)
        output_group.setLayout(output_layout)
        controls_layout.addWidget(output_group)

        # Subfolder List (with exclude buttons like PDF list)
        subfolder_group = QGroupBox("Subfolders to Process")
        self._style_group_box(subfolder_group)
        subfolder_layout = QVBoxLayout()
        
        # Summary label at top
        self.img_rip_folder_summary_label = QLabel("No folder selected")
        self.img_rip_folder_summary_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #6c757d; padding: 5px;")
        self.img_rip_folder_summary_label.setWordWrap(True)
        subfolder_layout.addWidget(self.img_rip_folder_summary_label)
        
        # List widget for subfolders
        self.img_rip_subfolder_list_widget = QListWidget()
        self.img_rip_subfolder_list_widget.setMinimumHeight(120)
        self.img_rip_subfolder_list_widget.setMaximumHeight(180)
        subfolder_layout.addWidget(self.img_rip_subfolder_list_widget)
        
        subfolder_group.setLayout(subfolder_layout)
        controls_layout.addWidget(subfolder_group)

        # Rotation
        rot_group = QGroupBox("Image Rotation")
        self._style_group_box(rot_group)
        rot_layout = QVBoxLayout()
        from PySide6.QtWidgets import QRadioButton, QButtonGroup
        self.img_rip_rotation_buttons = QButtonGroup(self)
        self.img_rip_rot_0 = QRadioButton("0° (No rotation)")
        self.img_rip_rot_90 = QRadioButton("90° (Clockwise)")
        self.img_rip_rot_180 = QRadioButton("180° (Upside down)")
        self.img_rip_rot_270 = QRadioButton("270° (Counter-clockwise)")
        self.img_rip_rot_0.setChecked(True)
        for i, btn in enumerate([self.img_rip_rot_0, self.img_rip_rot_90, self.img_rip_rot_180, self.img_rip_rot_270]):
            rot_layout.addWidget(btn)
            self.img_rip_rotation_buttons.addButton(btn, [0, 90, 180, 270][i])
            # Connect rotation change to preview update
            btn.toggled.connect(self._on_img_rip_rotation_changed)
        rot_group.setLayout(rot_layout)
        controls_layout.addWidget(rot_group)

        # Reverse Order option
        reverse_group = QGroupBox("File Order")
        self._style_group_box(reverse_group)
        reverse_layout = QVBoxLayout()
        self.img_rip_reverse_order_checkbox = QCheckBox("Reverse Order (Process files in reverse)")
        self.img_rip_reverse_order_checkbox.setChecked(False)
        self.img_rip_reverse_order_checkbox.setToolTip("Process images in reverse alphabetical order")
        reverse_layout.addWidget(self.img_rip_reverse_order_checkbox)
        reverse_group.setLayout(reverse_layout)
        controls_layout.addWidget(reverse_group)

        # Server Selection group
        img_rip_server_select_group = QGroupBox("🖥️ GIS Server Selection")
        self._style_group_box(img_rip_server_select_group)
        img_rip_server_select_layout = QVBoxLayout()
        
        # Load servers from config
        from pages.multi_server_print.server_manager import PrintServerManager
        self.img_rip_server_manager = PrintServerManager()
        
        # Server list with checkboxes
        self.img_rip_server_list = QListWidget()
        self.img_rip_server_list.setMaximumHeight(120)
        self.img_rip_server_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
        """)
        self._load_img_rip_servers()
        img_rip_server_select_layout.addWidget(QLabel("Select servers for RIP processing:"))
        img_rip_server_select_layout.addWidget(self.img_rip_server_list)
        
        # Distribution mode
        img_rip_dist_layout = QHBoxLayout()
        img_rip_dist_layout.addWidget(QLabel("Distribution:"))
        self.img_rip_distribution_combo = QComboBox()
        self.img_rip_distribution_combo.addItems(["Alternate (Round-Robin)", "Chunks"])
        self.img_rip_distribution_combo.setCurrentIndex(0)  # Default to Alternate
        img_rip_dist_layout.addWidget(self.img_rip_distribution_combo)
        img_rip_server_select_layout.addLayout(img_rip_dist_layout)
        
        # Refresh button
        img_rip_refresh_btn = QPushButton("🔄 Refresh Servers")
        img_rip_refresh_btn.clicked.connect(self._refresh_img_rip_servers)
        img_rip_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        img_rip_server_select_layout.addWidget(img_rip_refresh_btn)
        
        img_rip_server_select_group.setLayout(img_rip_server_select_layout)
        controls_layout.addWidget(img_rip_server_select_group)

        # Progress
        progress_group = QGroupBox("RIP Progress")
        self._style_group_box(progress_group)
        pg_layout = QVBoxLayout()
        self.img_rip_progress_bar = QProgressBar()
        self.img_rip_progress_bar.setVisible(False)
        self.img_rip_progress_bar.setStyleSheet("QProgressBar { color: #000000; font-weight: bold; }")
        self.img_rip_progress_status_label = QLabel("Ready to start RIP conversion")
        self.img_rip_progress_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        pg_layout.addWidget(self.img_rip_progress_bar)
        pg_layout.addWidget(self.img_rip_progress_status_label)
        progress_group.setLayout(pg_layout)
        controls_layout.addWidget(progress_group)

        # Live Monitoring
        monitor_group = QGroupBox("Live Processing Monitor")
        self._style_group_box(monitor_group)
        monitor_layout = QVBoxLayout()
        
        # Connections (fixed)
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Connections:"))
        self.img_rip_connections_label = QLabel("--")
        self.img_rip_connections_label.setStyleSheet("color: #0066cc; font-weight: bold; font-size: 11pt;")
        conn_layout.addWidget(self.img_rip_connections_label)
        conn_layout.addStretch()
        monitor_layout.addLayout(conn_layout)
        
        # Workers (adaptive)
        workers_layout = QHBoxLayout()
        workers_layout.addWidget(QLabel("Workers:"))
        self.img_rip_workers_label = QLabel("--")
        self.img_rip_workers_label.setStyleSheet("color: #00aa00; font-weight: bold; font-size: 11pt;")
        workers_layout.addWidget(self.img_rip_workers_label)
        workers_layout.addStretch()
        monitor_layout.addLayout(workers_layout)
        
        # Delay (adaptive)
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("Delay:"))
        self.img_rip_delay_label = QLabel("--")
        self.img_rip_delay_label.setStyleSheet("color: #ff6600; font-weight: bold; font-size: 11pt;")
        delay_layout.addWidget(self.img_rip_delay_label)
        delay_layout.addStretch()
        monitor_layout.addLayout(delay_layout)
        
        monitor_group.setLayout(monitor_layout)
        controls_layout.addWidget(monitor_group)

        # Actions
        actions_group = QGroupBox("Actions")
        self._style_group_box(actions_group)
        actions_layout = QVBoxLayout()
        self.start_img_rip_conversion_btn = QPushButton("Start IMAGE to RIP Conversion")
        self.start_img_rip_conversion_btn.clicked.connect(self._start_img_rip_conversion)
        self.stop_img_rip_conversion_btn = QPushButton("STOP")
        self.stop_img_rip_conversion_btn.setObjectName("StopButton")
        self.stop_img_rip_conversion_btn.clicked.connect(self._stop_img_rip_conversion)
        self.stop_img_rip_conversion_btn.setEnabled(False)
        self.open_img_rip_output_btn = QPushButton("Open Output Folder")
        self.open_img_rip_output_btn.clicked.connect(self._open_img_rip_output_folder)
        actions_layout.addWidget(self.start_img_rip_conversion_btn)
        actions_layout.addWidget(self.stop_img_rip_conversion_btn)
        actions_layout.addWidget(self.open_img_rip_output_btn)
        actions_group.setLayout(actions_layout)
        controls_layout.addWidget(actions_group)

        controls_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(controls_widget)
        left_scroll.setMinimumWidth(320)
        layout.addWidget(left_scroll, 0)

        # Right preview - Image Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_group = QGroupBox("Image Preview")
        self._style_group_box(preview_group)
        preview_content_layout = QVBoxLayout()
        
        self.img_rip_preview_label = QLabel("No folder selected\n\nSelect a folder to preview an image")
        self.img_rip_preview_label.setAlignment(Qt.AlignCenter)
        self.img_rip_preview_label.setStyleSheet("border: 1px solid #dee2e6; background-color: #f8f9fa; padding: 20px;")
        self.img_rip_preview_scroll = QScrollArea()
        self.img_rip_preview_scroll.setWidgetResizable(True)
        self.img_rip_preview_scroll.setWidget(self.img_rip_preview_label)
        self.img_rip_preview_scroll.setMinimumHeight(400)
        preview_content_layout.addWidget(self.img_rip_preview_scroll)
        preview_group.setLayout(preview_content_layout)
        preview_layout.addWidget(preview_group)

        layout.addWidget(preview_widget, 1)
        layout.setStretch(0, 3)
        layout.setStretch(1, 7)

        self.img_rip_output_dir = None

        outer_layout.addWidget(container, 1)
        return outer

    def closeEvent(self, event):
        try:
            self._cancel_requested = True
            if hasattr(self, 'conversion_worker') and self.conversion_worker:
                self.conversion_worker.cancel()
            if hasattr(self, 'conversion_thread') and self.conversion_thread.isRunning():
                self.conversion_thread.quit()
                self.conversion_thread.wait(500)
            
            # Also handle ripped conversion cleanup
            self._ripped_cancel_requested = True
            if hasattr(self, 'ripped_conversion_worker') and self.ripped_conversion_worker:
                self.ripped_conversion_worker.cancel()
            if hasattr(self, 'ripped_conversion_thread') and self.ripped_conversion_thread.isRunning():
                self.ripped_conversion_thread.quit()
                self.ripped_conversion_thread.wait(500)
            
            # Also handle image to rip cleanup
            self._img_rip_cancel_requested = True
            if hasattr(self, 'img_rip_conversion_worker') and self.img_rip_conversion_worker:
                self.img_rip_conversion_worker.cancel()
            if hasattr(self, 'img_rip_conversion_thread') and self.img_rip_conversion_thread.isRunning():
                self.img_rip_conversion_thread.quit()
                self.img_rip_conversion_thread.wait(500)
        except Exception:
            pass
        super().closeEvent(event)