import flet as ft
import threading
import time
import serial
import logging
import os
import platform
from typing import List, Optional
from dataclasses import dataclass

# Log configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _get_default_serial_port() -> str:
    """Get default serial port based on the operating system"""
    system = platform.system().lower()
    if system == "linux":
        return "/dev/ttyS0"
    elif system == "darwin":  # macOS
        return "/dev/tty.usbserial-0001"
    else:  # Windows
        return "COM5"

@dataclass
class Config:
    # Image settings
    image_path1: str = "frame1.png"
    image_path2: str = "frame2.png"
    
    # Serial settings
    serial_port: str = os.getenv("SERIAL_PORT", _get_default_serial_port())
    baud_rate: int = 115200
    
    # Animation settings
    frame_delay: float = 0.2
    text_clear_delay: int = 5
    max_lines: int = 3
    
    # UI settings
    window_width: int = 1280
    window_height: int = 960
    text_column_height: int = 100
    text_size: int = 24
    layout_spacing: int = 20

config = Config()

class AnimationApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.user_texts: List[str] = []
        self.bot_texts: List[str] = []
        self.listening_counter: int = 0
        
        # Threading events
        self.stop_event = threading.Event()
        self.terminate_event = threading.Event()
        self.stop_event.set()  # Start in paused state
        
        # UI components
        self.img: Optional[ft.Image] = None
        self.img_container: Optional[ft.Container] = None
        self.user_text_column: Optional[ft.Column] = None
        self.bot_text_column: Optional[ft.Column] = None
        
        self._setup_ui()
        self._start_threads()
    
    def _setup_ui(self) -> None:
        self.page.title = "RaspiProjection Flet Animation"
        self.page.bgcolor = "black"
        self.page.window_full_screen = True
        self.page.window_title_bar_hidden = True

        self.img = ft.Image(
            src=config.image_path1, 
            width=config.window_width, 
            height=config.window_height, 
            fit=ft.ImageFit.CONTAIN
        )
        self.img_container = ft.Container(self.img, alignment=ft.alignment.center, expand=True)

        self.user_text_column = ft.Column(
            [], 
            alignment=ft.MainAxisAlignment.START, 
            height=config.text_column_height, 
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.bot_text_column = ft.Column(
            [], 
            alignment=ft.MainAxisAlignment.START, 
            height=config.text_column_height, 
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )

        layout = ft.Column([
            self.bot_text_column,
            self.img_container,
            self.user_text_column
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=config.layout_spacing)
        self.page.add(layout)

        self.page.on_window_event = self._on_close
    
    def _start_threads(self) -> None:
        threading.Thread(target=self._animate, daemon=True).start()
        threading.Thread(target=self._serial_thread, daemon=True).start()
        logger.info("Animation and serial threads started")
    
    def update_texts(self) -> None:
        if self.user_text_column and self.bot_text_column:
            self.user_text_column.controls.clear()
            for t in self.user_texts:
                self.user_text_column.controls.append(ft.Text(t, color="yellow", size=config.text_size))
            self.bot_text_column.controls.clear()
            for t in self.bot_texts:
                self.bot_text_column.controls.append(ft.Text(t, color="white", size=config.text_size, text_align=ft.TextAlign.RIGHT))
            self.page.update()

    def clear_texts(self) -> None:
        self.user_texts.clear()
        self.bot_texts.clear()
        self.update_texts()

    def _animate(self) -> None:
        while not self.terminate_event.is_set():
            if not self.stop_event.is_set():
                if self.img:
                    self.img.src = config.image_path1
                    self.page.update()
                    time.sleep(config.frame_delay)
                    self.img.src = config.image_path2
                    self.page.update()
                    time.sleep(config.frame_delay)
            else:
                if self.img:
                    self.img.src = config.image_path1
                    self.page.update()
                    time.sleep(config.frame_delay)

    def _serial_thread(self) -> None:
        ser = None
        try:
            ser = serial.Serial(config.serial_port, config.baud_rate, timeout=1)
            logger.info(f"Serial port {config.serial_port} opened successfully")
        except serial.SerialException as e:
            logger.error(f"Serial port error: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error opening serial port: {e}")
            return
        
        try:
            self._process_serial_data(ser)
        except Exception as e:
            logger.error(f"Error in serial processing: {e}")
        finally:
            if ser and ser.is_open:
                ser.close()
                logger.info("Serial connection closed")
    
    def _process_serial_data(self, ser: serial.Serial) -> None:
        while not self.terminate_event.is_set():
            try:
                if ser.in_waiting > 0:
                    received = ser.readline().decode('utf-8', errors='ignore').strip()
                    if received:  # Ignore empty strings
                        logger.debug(f"Received: {received}")
                        self._handle_serial_message(received)
                else:
                    time.sleep(0.01)
            except UnicodeDecodeError as e:
                logger.warning(f"Unicode decode error: {e}")
                continue
            except serial.SerialException as e:
                logger.error(f"Serial communication error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in serial processing: {e}")
                break
    
    def _handle_serial_message(self, received: str) -> None:
        if "Application: STATE: listening" in received:
            logger.info("Animation paused - listening state")
            self.stop_event.set()
            self.listening_counter += 1
            my_counter = self.listening_counter
            def clear_after_delay(counter_snapshot: int) -> None:
                time.sleep(config.text_clear_delay)
                if self.stop_event.is_set() and self.listening_counter == counter_snapshot:
                    self.clear_texts()
                    logger.info("Text cleared after listening timeout")
            threading.Thread(target=clear_after_delay, args=(my_counter,), daemon=True).start()
        elif "Application: STATE: speaking" in received:
            logger.info("Animation resumed - speaking state")
            self.stop_event.clear()
            self.listening_counter = 0
        elif "Application: >>" in received:
            logger.debug("User text received")
            idx = received.find("Application: >>")
            text = received[idx + len("Application: >>"):].strip()
            if text:  # Ignore empty strings
                self.user_texts.append(text)
                if len(self.user_texts) > config.max_lines:
                    self.user_texts[:] = self.user_texts[-config.max_lines:]
                self.update_texts()
        elif "Application: <<" in received:
            logger.debug("Bot text received")
            idx = received.find("Application: <<")
            text = received[idx + len("Application: <<"):].strip()
            if text:  # Ignore empty strings
                self.bot_texts.append(text)
                if len(self.bot_texts) > config.max_lines:
                    self.bot_texts[:] = self.bot_texts[-config.max_lines:]
                self.update_texts()
    
    def _on_close(self, e) -> None:
        self.terminate_event.set()

def main(page: ft.Page) -> None:
    app = AnimationApp(page)

if __name__ == "__main__":
    # Force lightweight app mode for Raspberry Pi compatibility
    ft.app(
        target=main, 
        view=ft.AppView.FLET_APP_HIDDEN,  # Hidden window mode
        assets_dir="assets"
    )