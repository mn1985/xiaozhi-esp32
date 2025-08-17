import os
import platform
import serial
import threading
import time
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from typing import List
import logging

# Configuration
class Config:
    # Image files
    image_path1: str = "frame1.png"
    image_path2: str = "frame2.png"
    
    # Serial settings
    serial_port: str = os.getenv("SERIAL_PORT", "/dev/ttyS0" if platform.system() == "Linux" else "COM5")
    baud_rate: int = 115200
    
    # Display settings
    window_width: int = 1024
    window_height: int = 768
    text_size: int = 32
    frame_delay: float = 0.2
    text_clear_delay: int = 8
    max_lines: int = 3
    
    # Layout settings
    image_offset_y: int = 0  # Pixels to move image down from center
    user_text_margin_bottom: int = 100  # Margin from bottom of screen
    bot_text_margin_top: int = 0  # Margin from top for bot text
    user_text_margin_side: int = 15  # Margin inside text background
    text_padding_x: int = 50  # Left padding for text
    text_line_spacing: int = 0  # Space between text lines
    
    # Background settings
    background_opacity: int = 180  # Semi-transparent background (0-255)
    background_padding: int = 20  # Extra padding around text area
    
    # Text outline settings
    outline_offsets: list = [(-1,-1), (-1,1), (1,-1), (1,1)]

config = Config()

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class AnimationApp:
    def __init__(self):
        self.user_texts: List[str] = []
        self.bot_texts: List[str] = []
        self.listening_counter: int = 0
        
        # Event control
        self.stop_event = threading.Event()
        self.terminate_event = threading.Event()
        self.stop_event.set()  # Start paused
        
        self._load_images()
        self._load_font()
        self._setup_gui()
        self._start_threads()
        
    def _load_images(self):
        """Load and resize images"""
        self.img1 = Image.open(config.image_path1).resize((config.window_width, config.window_height))
        self.img2 = Image.open(config.image_path2).resize((config.window_width, config.window_height))
        
    def _load_font(self):
        """Load Japanese font"""
        font_paths = [
            "C:/Windows/Fonts/msgothic.ttc",  # Windows
            "/usr/share/fonts/opentype/note/NotoSansCJKjp-Regular.otf",  # Linux
            "/System/Library/Fonts/Arial Unicode MS.ttf",  # macOS
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                try:
                    self.font = ImageFont.truetype(path, config.text_size)
                    logger.info(f"Font loaded: {path}")
                    return
                except:
                    continue
        
        self.font = ImageFont.load_default()
        logger.warning("Using default font")
        
    def _setup_gui(self):
        """Setup GUI"""
        self.root = tk.Tk()
        self.root.title("RaspiProjection")
        self.root.configure(bg='black')
        self.root.geometry(f"{config.window_width}x{config.window_height}")
        self.root.attributes('-fullscreen', True)
        self.root.bind('<Escape>', self._on_exit)
        
        self.canvas = tk.Canvas(
            self.root,
            width=config.window_width,
            height=config.window_height,
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack()
        
        # Initial image display
        self.photo1 = ImageTk.PhotoImage(self.img1)
        self.image_item = self.canvas.create_image(
            config.window_width // 2,
            config.window_height // 2 + config.image_offset_y,
            image=self.photo1
        )
        
    def _start_threads(self):
        """Start threads"""
        threading.Thread(target=self._animate, daemon=True).start()
        threading.Thread(target=self._serial_loop, daemon=True).start()
        logger.info("Application started")
        
    def _create_text_image(self, base_image: Image.Image) -> ImageTk.PhotoImage:
        """Create image with text overlay"""
        img = base_image.copy()
        draw = ImageDraw.Draw(img)
        
        # Bot text area (top with background)
        if self.bot_texts:
            # Calculate text area size
            text_height = len(self.bot_texts) * (config.text_size + config.text_line_spacing) + config.background_padding
            # Draw semi-transparent background
            overlay = Image.new('RGBA', (config.window_width, text_height), (0, 0, 0, config.background_opacity))
            img.paste(overlay, (0, 0), overlay)
            
            # Draw bot text
            y = config.bot_text_margin_top
            for text in self.bot_texts:
                # Draw text outline for better visibility
                for dx, dy in config.outline_offsets:
                    draw.text((config.text_padding_x+dx, y+dy), text, font=self.font, fill='black')
                draw.text((config.text_padding_x, y), text, font=self.font, fill='white')
                y += config.text_size + config.text_line_spacing
            
        # User text area (bottom with background)
        if self.user_texts:
            # Calculate text area size
            text_height = len(self.user_texts) * (config.text_size + config.text_line_spacing) + config.background_padding
            start_y = config.window_height - text_height - config.user_text_margin_bottom
            # Draw semi-transparent background
            overlay = Image.new('RGBA', (config.window_width, text_height), (0, 0, 0, config.background_opacity))
            img.paste(overlay, (0, start_y), overlay)
            
            # Draw user text
            y = start_y + config.user_text_margin_side
            for text in self.user_texts:
                # Draw text outline for better visibility
                for dx, dy in config.outline_offsets:
                    draw.text((config.text_padding_x+dx, y+dy), text, font=self.font, fill='black')
                draw.text((config.text_padding_x, y), text, font=self.font, fill='yellow')
                y += config.text_size + config.text_line_spacing
            
        return ImageTk.PhotoImage(img)
        
    def _animate(self):
        """Animation loop"""
        frame = 0
        while not self.terminate_event.is_set():
            try:
                if self.stop_event.is_set():
                    # Paused: show frame 1 only
                    photo = self._create_text_image(self.img1)
                else:
                    # Animating: alternate frames
                    current_img = self.img1 if frame % 2 == 0 else self.img2
                    photo = self._create_text_image(current_img)
                    frame += 1
                    
                self.canvas.itemconfig(self.image_item, image=photo)
                self.canvas.image = photo
                time.sleep(config.frame_delay)
                
            except Exception as e:
                logger.error(f"Animation error: {e}")
                break
                
    def _serial_loop(self):
        """Serial communication loop"""
        try:
            with serial.Serial(config.serial_port, config.baud_rate, timeout=1) as ser:
                logger.info(f"Serial connected: {config.serial_port}")
                
                while not self.terminate_event.is_set():
                    if ser.in_waiting > 0:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            self._handle_message(line)
                    time.sleep(0.01)
                    
        except Exception as e:
            logger.error(f"Serial error: {e}")
            
    def _handle_message(self, msg: str):
        """Handle serial message"""
        if "STATE: listening" in msg:
            self.stop_event.set()
            self.listening_counter += 1
            counter = self.listening_counter
            
            # Clear text after delay
            def clear_later():
                time.sleep(config.text_clear_delay)
                if self.stop_event.is_set() and self.listening_counter == counter:
                    self.user_texts.clear()
                    self.bot_texts.clear()
                    
            threading.Thread(target=clear_later, daemon=True).start()
            
        elif "STATE: speaking" in msg:
            self.stop_event.clear()
            self.listening_counter = 0
            
        elif "Application: >>" in msg:
            text = msg.split("Application: >>", 1)[1].strip()
            if text:
                self.user_texts.append(text)
                self.user_texts = self.user_texts[-config.max_lines:]
                
        elif "Application: <<" in msg:
            text = msg.split("Application: <<", 1)[1].strip()
            if text:
                self.bot_texts.append(text)
                self.bot_texts = self.bot_texts[-config.max_lines:]
                
    def _on_exit(self, event=None):
        """Exit handler"""
        self.terminate_event.set()
        self.root.quit()
        
    def run(self):
        """Run application"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.terminate_event.set()

if __name__ == "__main__":
    try:
        app = AnimationApp()
        app.run()
    except Exception as e:
        logger.error(f"Error: {e}")
