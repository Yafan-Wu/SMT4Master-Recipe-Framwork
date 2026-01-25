# Code/GUI/Settings.py
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from qfluentwidgets import (
    CardWidget, IconWidget, BodyLabel, SwitchButton, CaptionLabel,
    TitleLabel, SubtitleLabel, DoubleSpinBox, 
    FluentIcon, setTheme, Theme, LineEdit, PushButton
)

class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page Title
        self.title = TitleLabel("Settings", self)
        layout.addWidget(self.title)
        
        # =============================================
        # 1. Theme Toggle (Dark Mode)
        # =============================================
        self.card_theme = CardWidget(self)
        l_theme = QHBoxLayout(self.card_theme)
        l_theme.setContentsMargins(20, 20, 20, 20)
        
        lbl_theme = SubtitleLabel("Dark Mode", self)
        
        self.switch_theme = SwitchButton(self)
        self.switch_theme.setChecked(True) 
        self.switch_theme.checkedChanged.connect(self.toggle_theme)
        
        l_theme.addWidget(lbl_theme)
        l_theme.addStretch(1)
        l_theme.addWidget(self.switch_theme)
        layout.addWidget(self.card_theme)
        
        # =============================================
        # 2. Export Path Setting
        # =============================================
        self.card_path = CardWidget(self)
        l_path = QVBoxLayout(self.card_path)

        l_path.setContentsMargins(20, 20, 20, 20)

        l_path.setSpacing(10) 
        
        # Header
        path_header = QHBoxLayout()

        path_header.setContentsMargins(0, 0, 0, 0)
        
        lbl_path_title = SubtitleLabel("Export Directory", self)
        
        self.switch_custom_path = SwitchButton(self)
        self.switch_custom_path.setOnText("Custom")
        self.switch_custom_path.setOffText("Default (Downloads)")
        self.switch_custom_path.checkedChanged.connect(self.toggle_path_mode)
        
        path_header.addWidget(lbl_path_title)
        path_header.addStretch(1)
        path_header.addWidget(self.switch_custom_path)
        
        # Path Selection Row
        path_selection = QHBoxLayout()

        path_selection.setContentsMargins(0, 0, 0, 0)
        
        self.line_path = LineEdit(self)
        self.line_path.setReadOnly(True)
        
        self.default_path = os.path.expanduser("~/Downloads")
        self.line_path.setText(self.default_path)
        
        self.btn_browse = PushButton("Browse", self)
        self.btn_browse.clicked.connect(self.browse_path)
        self.btn_browse.setEnabled(False) 
        
        path_selection.addWidget(self.line_path)
        path_selection.addWidget(self.btn_browse)
        
        l_path.addLayout(path_header)
        l_path.addLayout(path_selection)
        layout.addWidget(self.card_path)
        
        # =============================================
        # 3. Optimization Weights
        # =============================================
        self.card_weights = CardWidget(self)
        l_weights = QVBoxLayout(self.card_weights)

        l_weights.setContentsMargins(20, 20, 20, 20)
        l_weights.setSpacing(10)
        
        # Header
        weights_header = QHBoxLayout()

        weights_header.setContentsMargins(0, 0, 0, 0)
        
        w_title = SubtitleLabel("Optimization Weights (Sum = 1.0)", self)
        weights_header.addWidget(w_title)
        weights_header.addStretch(1)
        
        l_weights.addLayout(weights_header)
        
        # Helper to create weight rows
        def create_weight_row(label, default_val):
            row = QHBoxLayout()

            row.setContentsMargins(0, 0, 0, 0)
            
            lbl = BodyLabel(label, self)
            spin = DoubleSpinBox(self)
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.1)
            spin.setValue(default_val)
            
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(spin)
            return row, spin
            
        r1, self.spin_energy = create_weight_row("Energy Cost Weight", 0.4)
        r2, self.spin_use = create_weight_row("Use Cost Weight", 0.3)
        r3, self.spin_co2 = create_weight_row("CO2 Footprint Weight", 0.3)
        
        l_weights.addLayout(r1)
        l_weights.addLayout(r2)
        l_weights.addLayout(r3)
        layout.addWidget(self.card_weights)
        
        self.card_weights.setVisible(False)
        
        # Connect signals
        self.spin_energy.valueChanged.connect(lambda v: self.balance_weights(self.spin_energy, v))
        self.spin_use.valueChanged.connect(lambda v: self.balance_weights(self.spin_use, v))
        self.spin_co2.valueChanged.connect(lambda v: self.balance_weights(self.spin_co2, v))
        
        self.prev_vals = {
            self.spin_energy: 0.4,
            self.spin_use: 0.3,
            self.spin_co2: 0.3
        }
        
        layout.addStretch()

    def toggle_path_mode(self, checked):
        """Enable or disable the browse button based on the switch state."""
        self.btn_browse.setEnabled(checked)
        if not checked:
            self.line_path.setText(self.default_path)

    def browse_path(self):
        """Open a dialog to select a custom export directory."""
        d = QFileDialog.getExistingDirectory(self, "Select Export Directory", self.line_path.text())
        if d:
            self.line_path.setText(d)

    def get_export_path(self):
        """Return the current export path."""
        return self.line_path.text()

    def set_weights_visible(self, visible: bool):
        """Show or hide the weights card (called by main window based on mode)."""
        self.card_weights.setVisible(visible)

    def balance_weights(self, source_spin, new_val):
        """Automatically adjust other weights so the sum remains 1.0."""
        old_val = self.prev_vals[source_spin]
        delta = new_val - old_val
        self.prev_vals[source_spin] = new_val
        
        if abs(delta) < 0.0001: return
        
        others = [s for s in [self.spin_energy, self.spin_use, self.spin_co2] if s != source_spin]
        
        for s in others: s.blockSignals(True)
        
        adjustment = delta / 2.0
        for s in others:
            curr = s.value()
            s.setValue(max(0.0, min(1.0, curr - adjustment)))
            self.prev_vals[s] = s.value()
            
        for s in others: s.blockSignals(False)

    def toggle_theme(self, checked):
        """Switch between Light and Dark themes."""
        if checked: setTheme(Theme.DARK)
        else: setTheme(Theme.LIGHT)
        
    def get_weights(self):
        """Return tuple of (energy, use, co2) weights."""
        return (self.spin_energy.value(), self.spin_use.value(), self.spin_co2.value())