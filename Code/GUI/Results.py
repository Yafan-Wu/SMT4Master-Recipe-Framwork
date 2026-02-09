# Code/GUI/Results.py
import os
from typing import List, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QHBoxLayout, QFileDialog
)
from qfluentwidgets import (
    TableWidget, SubtitleLabel, PrimaryPushButton, PushButton,
    InfoBar, InfoBarPosition
)

# Import Generator
from Code.Transformator.MasterRecipeGenerator import generate_b2mml_master_recipe

# Validation helpers
from Code.GUI.Workers import validate_master_recipe_xml, validate_master_recipe_parameters

# For on-demand parsing if no cached resources exist
try:
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
except Exception:
    parse_capabilities_robust = None


class ResultsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("results_page")

        # Store context data for export
        self.context_data = None
        self.current_color_hex = "#107C10"  # Default Green

        layout = QVBoxLayout(self)

        # Header with Title and Export Button
        header_layout = QHBoxLayout()
        self.title = SubtitleLabel("Calculation Results", self)

        self.btn_export = PrimaryPushButton("Export Master Recipe", self)
        self.btn_export.setFixedWidth(200)
        self.btn_export.setEnabled(False)  # Disabled until selection
        self.btn_export.clicked.connect(self.export_solution)

        self.btn_validate = PushButton("Validate Master Recipe", self)
        self.btn_validate.setFixedWidth(200)
        self.btn_validate.clicked.connect(self.validate_master_recipe)

        self.btn_param_validate = PushButton("Parameter Validierung", self)
        self.btn_param_validate.setFixedWidth(200)
        self.btn_param_validate.clicked.connect(self.validate_parameters)

        header_layout.addWidget(self.title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_validate)
        header_layout.addWidget(self.btn_param_validate)
        header_layout.addWidget(self.btn_export)

        self.table = TableWidget(self)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setWordWrap(True)


        try:
            self.table.setUniformRowHeights(False)
        except Exception:
            pass

        # Enable row selection
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(TableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

        layout.addLayout(header_layout)
        layout.addWidget(self.table, 1)

    def set_export_button_color(self, color_hex):
        """Called by Home to sync color"""
        self.current_color_hex = color_hex
        self.update_button_style()

    def update_button_style(self):
        style = f"""
            PrimaryPushButton {{
                background-color: {self.current_color_hex};
                border: 1px solid {self.current_color_hex};
                border-radius: 6px;
                color: white;
            }}
            PrimaryPushButton:hover {{
                background-color: {self.current_color_hex};
                opacity: 0.9;
            }}
            PrimaryPushButton:pressed {{
                background-color: {self.current_color_hex};
                opacity: 0.8;
            }}
            PrimaryPushButton:disabled {{
                background-color: #cccccc;
                border: 1px solid #cccccc;
                color: #666666;
            }}
        """
        self.btn_export.setStyleSheet(style)

    def set_data(self, gui_data: List[Dict], context_data: Dict):
        """Receive data from Home"""
        self.context_data = context_data
        self.update_table(gui_data)
        self.btn_export.setEnabled(False)

    def on_selection_changed(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.btn_export.setEnabled(False)
            return

        row = selected_items[0].row()
        item = self.table.item(row, 0)  # Col 0 is Sol ID

        if item and item.text().isdigit():
            self.btn_export.setEnabled(True)
        else:
            self.btn_export.setEnabled(False)

    def export_solution(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        sol_id_item = self.table.item(row, 0)
        if not sol_id_item:
            return

        sol_id_text = sol_id_item.text()
        if not sol_id_text.isdigit():
            return
        sol_id = int(sol_id_text)

        main_win = self.window()
        save_dir = ""
        if hasattr(main_win, 'settings_page'):
            save_dir = main_win.settings_page.get_export_path()
        else:
            save_dir = os.path.expanduser("~/Downloads")

        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir)
            except Exception:
                save_dir = os.path.expanduser("~/Downloads")

        filename = f"MasterRecipe_Sol_{sol_id}.xml"
        full_path = os.path.join(save_dir, filename)

        try:
            generate_b2mml_master_recipe(
                resources_data=self.context_data['resources'],
                solutions_data_list=self.context_data['solutions'],
                general_recipe_data=self.context_data['recipe'],
                selected_solution_id=sol_id,
                output_path=full_path
            )

            InfoBar.success(
                title="Export Successful",
                content=f"Saved to: {full_path}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self.window()
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error(
                title="Export Failed",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window()
            )

    # =========================
    # Master Recipe Validation
    # =========================
    def _append_log(self, msg: str):
        main = self.window()
        if hasattr(main, 'log_page') and hasattr(main.log_page, 'append_log'):
            main.log_page.append_log(msg)

    def validate_master_recipe(self):
        main = self.window()
        start_dir = os.path.expanduser("~/Downloads")
        if hasattr(main, 'settings_page'):
            try:
                d = main.settings_page.get_export_path()
                if d and os.path.isdir(d):
                    start_dir = d
            except Exception:
                pass

        xml_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Master Recipe XML",
            start_dir,
            "XML Files (*.xml);;All Files (*)"
        )
        if not xml_path:
            return

        schema_dir = QFileDialog.getExistingDirectory(
            self,
            "Select allschema Folder (XSD set)",
            start_dir
        )
        if not schema_dir:
            return

        try:
            ok, errors, used_root = validate_master_recipe_xml(xml_path, schema_dir, root_xsd_path=None)

            self._append_log(f"[VALIDATION] XML: {xml_path}")
            self._append_log(f"[VALIDATION] allschema: {schema_dir}")
            self._append_log(f"[VALIDATION] root XSD used: {used_root}")

            if ok:
                InfoBar.success(
                    title="Validation Passed",
                    content=f"XML conforms to XSD (root: {os.path.basename(used_root)})",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window()
                )
                self._append_log("[VALIDATION] Result: PASSED")
                return

            preview = " | ".join(errors[:2])
            more = "" if len(errors) <= 2 else f" (+{len(errors)-2} more)"
            InfoBar.error(
                title="Validation Failed",
                content=f"{preview}{more}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=8000,
                parent=self.window()
            )
            self._append_log(f"[VALIDATION] Result: FAILED (errors={len(errors)})")
            for i, err in enumerate(errors[:50], start=1):
                self._append_log(f"  {i}. {err}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error(
                title="Validation Error",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window()
            )

    # =========================
    # Parameter Validation
    # =========================
    def validate_parameters(self):
        main = self.window()
        start_dir = os.path.expanduser("~/Downloads")
        if hasattr(main, 'settings_page'):
            try:
                d = main.settings_page.get_export_path()
                if d and os.path.isdir(d):
                    start_dir = d
            except Exception:
                pass

        xml_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Master Recipe XML",
            start_dir,
            "XML Files (*.xml);;All Files (*)"
        )
        if not xml_path:
            return

        resources_data = None
        if isinstance(self.context_data, dict) and 'resources' in self.context_data:
            resources_data = self.context_data.get('resources')

        if not resources_data:
            if parse_capabilities_robust is None:
                InfoBar.error(
                    title="Parameter Validation Error",
                    content="AAS parser (parse_capabilities_robust) not available in this build.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self.window()
                )
                return

            resource_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Resource Directory (AAS XML/AASX)",
                start_dir
            )
            if not resource_dir:
                return

            self._append_log(f"[PARAM-VALIDATION] Parsing resources from: {resource_dir}")
            resources_data = {}
            try:
                for fn in os.listdir(resource_dir):
                    if not (fn.lower().endswith('.xml') or fn.lower().endswith('.aasx')):
                        continue
                    full = os.path.join(resource_dir, fn)
                    res_name = os.path.splitext(fn)[0]
                    try:
                        caps = parse_capabilities_robust(full)
                        if caps:
                            resources_data[f"resource: {res_name}"] = caps
                    except Exception as pe:
                        self._append_log(f"[PARAM-VALIDATION] Warning: failed to parse {fn}: {pe}")
            except Exception as e:
                InfoBar.error(
                    title="Resource Parsing Failed",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self.window()
                )
                return

        try:
            ok, errors, warnings, checked, details = validate_master_recipe_parameters(xml_path, resources_data)

            self._append_log(f"[PARAM-VALIDATION] XML: {xml_path}")
            self._append_log(f"[PARAM-VALIDATION] Checked parameters: {checked}")

            found_items = [d for d in details if d.get('status') == 'FOUND']
            missing_items = [d for d in details if d.get('status') == 'MISSING']
            self._append_log(f"[PARAM-VALIDATION] Matched: {len(found_items)} | Missing: {len(missing_items)}")

            for d in found_items[:50]:
                cand = d.get('matched_candidate')
                rk = d.get('matched_resource')
                sc = d.get('score', 0.0)
                self._append_log(f"  OK: {d.get('description')} -> '{cand}' in {rk}, score={sc:.2f}")

            for w in warnings[:100]:
                self._append_log(f"  WARN: {w}")
            for e in errors[:200]:
                self._append_log(f"  ERROR: {e}")

            if ok:
                InfoBar.success(
                    title="Parameter Validation Passed",
                    content=f"All {checked} parameters matched parsed AAS capabilities.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window()
                )
            else:
                preview = " | ".join(errors[:2])
                more = "" if len(errors) <= 2 else f" (+{len(errors)-2} more)"
                InfoBar.error(
                    title="Parameter Validation Failed",
                    content=f"{preview}{more}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=9000,
                    parent=self.window()
                )

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._append_log("[PARAM-VALIDATION] Exception occurred:")
            self._append_log(traceback.format_exc())
            InfoBar.error(
                title="Parameter Validation Error",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window()
            )

    # =========================
    # TABLE UPDATE (FIXED FOR ULTRA)
    # =========================
    def update_table(self, data: List[Dict]):
        """
        Update result table.
        Ultra/Pro consistent: insert a separator row whenever solution_id changes.
        """

        # -------- detect score mode --------
        has_score = False
        if data:
            for row in data:
                if row:
                    has_score = ('composite_score' in row)
                    break

        # -------- rebuild data with separators by solution_id change (DO NOT rely on input {}) --------
        display_data: List[Dict] = []
        prev_sid = None
        for row in data:
            if not row:
                continue
            sid = row.get("solution_id", None)
            if prev_sid is not None and sid is not None and sid != prev_sid:
                display_data.append({})  # separator marker
            display_data.append(row)
            prev_sid = sid
        data = display_data

        # -------- headers/columns --------
        if has_score:
            headers = ["Sol ID", "Score", "Step", "Description", "Resource", "Capabilities", "Energy", "Use", "CO2"]
            self.table.setColumnCount(9)
        else:
            headers = ["Sol ID", "Step", "Description", "Resource", "Capabilities", "Status"]
            self.table.setColumnCount(6)

        # -------- clear old state --------
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        try:
            self.table.clearSpans()
        except Exception:
            pass

        self.table.setHorizontalHeaderLabels(headers)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cap_col_idx = 5 if has_score else 4
        self.table.horizontalHeader().setSectionResizeMode(cap_col_idx, QHeaderView.ResizeMode.Stretch)

        # Make row height controllable
        try:
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        except Exception:
            pass

        self.table.setRowCount(len(data))

        # -------- separator style --------

        separator_height = 24
        sep_bg = QColor("#f3f3f3")
        try:
            from qfluentwidgets import isDarkTheme
            if isDarkTheme():
                sep_bg = QColor("#2a2a2a")
        except Exception:
            pass

        # -------- fill table --------
        for r, row_data in enumerate(data):
            # separator row: fill every column with empty item (no spans!)
            if not row_data:
                self.table.setRowHeight(r, separator_height)
                for c in range(self.table.columnCount()):
                    it = QTableWidgetItem("")
                    it.setFlags(Qt.ItemFlag.NoItemFlags)
                    it.setBackground(sep_bg)
                    self.table.setItem(r, c, it)
                continue

            # normal rows
            if has_score:
                self.table.setItem(r, 0, QTableWidgetItem(str(row_data.get('solution_id', ''))))
                self.table.setItem(r, 1, QTableWidgetItem(f"{row_data.get('composite_score', 0):.2f}"))
                self.table.setItem(r, 2, QTableWidgetItem(str(row_data.get('step_id', ''))))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data.get('description', ''))))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data.get('resource', ''))))
                self.table.setItem(r, 5, QTableWidgetItem(str(row_data.get('capabilities', ''))))
                self.table.setItem(r, 6, QTableWidgetItem(f"{row_data.get('energy_cost', 0):.1f}"))
                self.table.setItem(r, 7, QTableWidgetItem(f"{row_data.get('use_cost', 0):.1f}"))
                self.table.setItem(r, 8, QTableWidgetItem(f"{row_data.get('co2_footprint', 0):.1f}"))
            else:
                self.table.setItem(r, 0, QTableWidgetItem(str(row_data.get('solution_id', ''))))
                self.table.setItem(r, 1, QTableWidgetItem(str(row_data.get('step_id', ''))))
                self.table.setItem(r, 2, QTableWidgetItem(str(row_data.get('description', ''))))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data.get('resource', ''))))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data.get('capabilities', ''))))
                status_item = QTableWidgetItem(str(row_data.get('status', '')))
                status_item.setForeground(QColor("#28a745"))
                self.table.setItem(r, 5, status_item)

        self.table.resizeRowsToContents()
        for r, row_data in enumerate(data):
            if not row_data:
                self.table.setRowHeight(r, separator_height)

        self.table.setSortingEnabled(True)
