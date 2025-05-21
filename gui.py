import tkinter as tk
from tkinter import ttk
import queue
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

class CrawlerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Website Crawler Progress")
        self.root.geometry("1200x800")
        
        # Create message queue for thread-safe communication
        self.message_queue = queue.Queue()
        
        # Create main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create progress frame
        self.progress_frame = ttk.LabelFrame(self.main_frame, text="Crawl Progress", padding="5")
        self.progress_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Create log frame
        self.log_frame = ttk.LabelFrame(self.main_frame, text="Logs", padding="5")
        self.log_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)
        
        # Create progress widgets
        self.create_progress_widgets()
        
        # Create log widgets
        self.create_log_widgets()
        
        # Domain progress frames
        self.domain_frames: Dict[str, ttk.Frame] = {}
        
        # Set up periodic update
        self.root.after(100, self.update_gui)
    
    def create_progress_widgets(self):
        # Global stats
        self.global_stats_frame = ttk.Frame(self.progress_frame)
        self.global_stats_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Total pages crawled
        ttk.Label(self.global_stats_frame, text="Total Pages Crawled:").grid(row=0, column=0, sticky=tk.W)
        self.total_pages_label = ttk.Label(self.global_stats_frame, text="0")
        self.total_pages_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # Total pending URLs
        ttk.Label(self.global_stats_frame, text="Total Pending URLs:").grid(row=1, column=0, sticky=tk.W)
        self.total_pending_label = ttk.Label(self.global_stats_frame, text="0")
        self.total_pending_label.grid(row=1, column=1, sticky=tk.W, padx=5)
        
        # Elapsed time
        ttk.Label(self.global_stats_frame, text="Elapsed Time:").grid(row=2, column=0, sticky=tk.W)
        self.elapsed_time_label = ttk.Label(self.global_stats_frame, text="00:00:00")
        self.elapsed_time_label.grid(row=2, column=1, sticky=tk.W, padx=5)
        
        # Estimated time remaining
        ttk.Label(self.global_stats_frame, text="Estimated Time Remaining:").grid(row=3, column=0, sticky=tk.W)
        self.remaining_time_label = ttk.Label(self.global_stats_frame, text="00:00:00")
        self.remaining_time_label.grid(row=3, column=1, sticky=tk.W, padx=5)
        
        # Domain progress container
        self.domain_progress_frame = ttk.Frame(self.progress_frame)
        self.domain_progress_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Add scrollbar for domain progress
        self.domain_canvas = tk.Canvas(self.domain_progress_frame)
        self.domain_scrollbar = ttk.Scrollbar(self.domain_progress_frame, orient="vertical", command=self.domain_canvas.yview)
        self.domain_scrollable_frame = ttk.Frame(self.domain_canvas)
        
        self.domain_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.domain_canvas.configure(scrollregion=self.domain_canvas.bbox("all"))
        )
        
        self.domain_canvas.create_window((0, 0), window=self.domain_scrollable_frame, anchor="nw")
        self.domain_canvas.configure(yscrollcommand=self.domain_scrollbar.set)
        
        self.domain_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.domain_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.domain_progress_frame.columnconfigure(0, weight=1)
        self.domain_progress_frame.rowconfigure(0, weight=1)
    
    def create_log_widgets(self):
        # Create text widget for logs
        self.log_text = tk.Text(self.log_frame, wrap=tk.WORD, height=10)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Add scrollbar
        self.log_scrollbar = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_text.yview)
        self.log_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)
        
        # Configure grid weights
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)
    
    def update_domain_progress(self, domain: str, stats: dict):
        if domain not in self.domain_frames:
            frame = ttk.Frame(self.domain_scrollable_frame)
            frame.grid(row=len(self.domain_frames), column=0, sticky=(tk.W, tk.E), padx=5, pady=2)
            
            # Domain name
            ttk.Label(frame, text=f"Domain: {domain}").grid(row=0, column=0, sticky=tk.W)
            
            # Progress bar
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100)
            progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5)
            
            # Stats labels
            stats_frame = ttk.Frame(frame)
            stats_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=5)
            
            pages_label = ttk.Label(stats_frame, text="Pages: 0/50")
            pages_label.grid(row=0, column=0, sticky=tk.W, padx=5)
            
            pending_label = ttk.Label(stats_frame, text="Pending: 0")
            pending_label.grid(row=0, column=1, sticky=tk.W, padx=5)
            
            speed_label = ttk.Label(stats_frame, text="Speed: 0.0 pages/s")
            speed_label.grid(row=0, column=2, sticky=tk.W, padx=5)
            
            self.domain_frames[domain] = {
                'frame': frame,
                'progress_var': progress_var,
                'progress_bar': progress_bar,
                'pages_label': pages_label,
                'pending_label': pending_label,
                'speed_label': speed_label
            }
        
        widgets = self.domain_frames[domain]
        widgets['progress_var'].set(stats['progress_percentage'])
        widgets['pages_label'].config(text=f"Pages: {stats['pages_crawled']}/50")
        widgets['pending_label'].config(text=f"Pending: {stats['pending_urls']}")
        widgets['speed_label'].config(text=f"Speed: {stats['pages_per_second']:.1f} pages/s")
    
    def update_global_stats(self, stats: dict):
        self.total_pages_label.config(text=str(stats['total_pages_crawled']))
        self.total_pending_label.config(text=str(stats['total_pending_urls']))
        self.elapsed_time_label.config(text=stats['elapsed_time'])
        self.remaining_time_label.config(text=stats['estimated_time_remaining'])
    
    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def update_gui(self):
        try:
            while True:
                message = self.message_queue.get_nowait()
                if message['type'] == 'domain_progress':
                    self.update_domain_progress(message['domain'], message['stats'])
                elif message['type'] == 'global_stats':
                    self.update_global_stats(message['stats'])
                elif message['type'] == 'log':
                    self.add_log(message['message'])
        except queue.Empty:
            pass
        
        self.root.after(100, self.update_gui)
    
    async def run_async(self):
        """Run the GUI in a non-blocking way with asyncio."""
        while True:
            self.root.update()
            await asyncio.sleep(0.1)
    
    def close(self):
        self.root.quit()

class GUILogHandler(logging.Handler):
    def __init__(self, message_queue: queue.Queue):
        super().__init__()
        self.message_queue = message_queue
    
    def emit(self, record):
        msg = self.format(record)
        self.message_queue.put({'type': 'log', 'message': msg}) 