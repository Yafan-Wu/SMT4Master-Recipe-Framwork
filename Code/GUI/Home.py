# Code/GUI/Home.py
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QSlider, QProgressBar 
from qfluentwidgets import (
    CardWidget, IconWidget, BodyLabel, CaptionLabel, 
    PrimaryPushButton, PushButton, Slider, 
    TitleLabel, FluentIcon, InfoBar, InfoBarPosition, setThemeColor,
    FluentWindow
)

from Code.GUI.Workers import SMTWorker

class ZoneSlider(Slider):
    def mousePressEvent(self, event):
        if self.orientation() == Qt.Orientation.Horizontal:
            ratio = event.pos().x() / self.width()
            val = 1 
            if ratio < 0.35: val = 0 
            elif ratio > 0.65: val = 2 
            else: val = 1 
            self.setValue(val)
            event.accept()
        else:
            super().mousePressEvent(event)

class HomePage(QWidget):
    def __init__(self, log_callback, settings_page, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self.log_callback = log_callback
        self.settings_page = settings_page
        self.recipe_path = ""
        self.resource_dir = ""
        
        setThemeColor("#00629B")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = TitleLabel("SMT4ModPlant Orchestrator", self)
        desc = CaptionLabel("Resource matching tool based on General Recipe and AAS Capabilities.", self)
        desc.setStyleSheet("color: #666;") 
        layout.addWidget(title)
        layout.addWidget(desc)

        # File Inputs
        self.card_recipe = CardWidget(self)
        l1 = QHBoxLayout(self.card_recipe)
        icon1 = IconWidget(FluentIcon.DOCUMENT, self)
        v1 = QVBoxLayout()
        self.lbl_recipe = BodyLabel("General Recipe XML", self)
        self.lbl_recipe_val = CaptionLabel("No file selected", self)
        v1.addWidget(self.lbl_recipe)
        v1.addWidget(self.lbl_recipe_val)
        btn1 = PushButton("Select File", self)
        btn1.clicked.connect(self.select_recipe)
        l1.addWidget(icon1)
        l1.addLayout(v1, 1)
        l1.addWidget(btn1)
        layout.addWidget(self.card_recipe)

        self.card_res = CardWidget(self)
        l2 = QHBoxLayout(self.card_res)
        icon2 = IconWidget(FluentIcon.FOLDER, self)
        v2 = QVBoxLayout()
        self.lbl_res = BodyLabel("Resources Directory (XML/AASX)", self)
        self.lbl_res_val = CaptionLabel("No folder selected", self)
        v2.addWidget(self.lbl_res)
        v2.addWidget(self.lbl_res_val)
        btn2 = PushButton("Select Folder", self)
        btn2.clicked.connect(self.select_folder)
        l2.addWidget(icon2)
        l2.addLayout(v2, 1)
        l2.addWidget(btn2)
        layout.addWidget(self.card_res)

        # Mode Slider
        self.card_opts = CardWidget(self)
        l_opts = QHBoxLayout(self.card_opts)
        icon_opts = IconWidget(FluentIcon.SPEED_HIGH, self)
        
        v_opts = QVBoxLayout()
        self.lbl_opts = BodyLabel("Optimization Mode", self)
        
        v_slider_container = QVBoxLayout()
        v_slider_container.setSpacing(5)
        
        self.slider_mode = ZoneSlider(Qt.Orientation.Horizontal, self)
        self.slider_mode.setRange(0, 2)
        self.slider_mode.setPageStep(1)
        self.slider_mode.setSingleStep(1)
        self.slider_mode.setValue(0)
        self.slider_mode.setFixedWidth(200)
        self.slider_mode.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_mode.setTickInterval(1)
        self.slider_mode.valueChanged.connect(self.update_ui_state)
        
        v_slider_container.addWidget(self.slider_mode)
        
        h_labels = QHBoxLayout()
        h_labels.setContentsMargins(0,0,0,0)
        lbl_fast = CaptionLabel("Fast", self)
        lbl_pro = CaptionLabel("Pro", self)
        lbl_ultra = CaptionLabel("Ultra", self)
        font = QFont()
        font.setPointSize(13)
        lbl_fast.setFont(font)
        lbl_pro.setFont(font)
        lbl_ultra.setFont(font)
        lbl_fast.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lbl_pro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ultra.setAlignment(Qt.AlignmentFlag.AlignRight)
        h_labels.addWidget(lbl_fast)
        h_labels.addWidget(lbl_pro)
        h_labels.addWidget(lbl_ultra)
        v_slider_container.addLayout(h_labels)
        
        self.lbl_opts_desc = CaptionLabel("Fast (1 Sol)", self)
        v_opts.addWidget(self.lbl_opts)
        v_opts.addWidget(self.lbl_opts_desc)
        
        l_opts.addWidget(icon_opts)
        l_opts.addLayout(v_opts, 1) 
        l_opts.addLayout(v_slider_container) 
        layout.addWidget(self.card_opts)

        self.btn_run = PrimaryPushButton("Start Calculation in Fast Mode", self)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)

        self.pbar = QProgressBar(self)
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)
        
        layout.addStretch()
        
        self.update_ui_state(0)

    def update_ui_state(self, val):
        modes = ["Fast", "Pro", "Ultra"]
        mode_text = modes[val]
        
        if self.settings_page:
            self.settings_page.set_weights_visible(val == 2)

        if val == 0: 
            color_hex = "#107C10" 
            desc = "Fast (Single Solution)"
        elif val == 1: 
            color_hex = "#00629B"
            desc = "Pro (All Valid Solutions)"
        else: 
            color_hex = "#FF8C00" 
            desc = "Ultra (Cost Optimization)"

        self.lbl_opts_desc.setText(desc)
        self.btn_run.setText(f"Start Calculation in {mode_text} Mode")
        
        btn_style = f"""
            PrimaryPushButton {{
                background-color: {color_hex};
                border: 1px solid {color_hex};
                border-radius: 6px;
                color: white;
                height: 40px;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }}
            PrimaryPushButton:hover {{
                background-color: {color_hex}; 
                border: 1px solid {color_hex};
            }}
            PrimaryPushButton:pressed {{
                background-color: {color_hex};
                opacity: 0.8;
            }}
            PrimaryPushButton:disabled {{
                background-color: {color_hex};
                opacity: 0.5; 
                border: 1px solid {color_hex};
                color: rgba(255, 255, 255, 0.8);
            }}
        """
        self.btn_run.setStyleSheet(btn_style)
        
        # [NEW] Notify Results Page about color change
        main_win = self.window()
        if isinstance(main_win, FluentWindow) and hasattr(main_win, 'results_page'):
            main_win.results_page.set_export_button_color(color_hex)
        
        slider_style = f"""
            Slider::groove:horizontal {{
                height: 4px; 
                background: #cccccc;
                border-radius: 2px;
            }}
            Slider::handle:horizontal {{
                background: {color_hex};
                border: 2px solid {color_hex};
                width: 18px;
                height: 18px;
                border-radius: 10px;
                margin: -7px 0;
            }}
            Slider::sub-page:horizontal {{
                background: {color_hex};
                border-radius: 2px;
            }}
        """
        self.slider_mode.setStyleSheet(slider_style)

    def select_recipe(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Recipe XML", os.getcwd(), "XML Files (*.xml)")
        if f:
            self.recipe_path = f
            self.lbl_recipe_val.setText(os.path.basename(f))
            self.check_ready()

    def select_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Resources Folder", os.getcwd())
        if d:
            self.resource_dir = d
            self.lbl_res_val.setText(d)
            self.check_ready()

    def check_ready(self):
        if self.recipe_path and self.resource_dir:
            self.btn_run.setEnabled(True)

    def run_process(self):
        self.btn_run.setEnabled(False)
        self.log_callback("Starting Process...")
        
        mode = self.slider_mode.value()
        weights = self.settings_page.get_weights()
        
        self.worker = SMTWorker(self.recipe_path, self.resource_dir, mode, weights)
        self.worker.log_signal.connect(self.log_callback)
        self.worker.progress_signal.connect(lambda c, t: (self.pbar.setMaximum(t), self.pbar.setValue(c)))
        self.worker.error_signal.connect(lambda e: InfoBar.error(title="Error", content=e, parent=self.window()))
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, results, context_data):
        self.btn_run.setEnabled(True)
        main = self.window()
        if isinstance(main, FluentWindow):
            if hasattr(main, 'results_page') and hasattr(main, 'switchTo'):
                # Pass both gui data and context data
                main.results_page.set_data(results, context_data)
                main.switchTo(main.results_page)
                InfoBar.success(title="Completed", content=f"Calculation finished.", parent=main, position=InfoBarPosition.TOP_RIGHT)