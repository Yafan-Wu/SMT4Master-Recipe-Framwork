# SMT4ModPlant GUI Orchestrator

**SMT4ModPlant** is an intelligent resource matching and master recipe generation tool designed for modular production plants. It parses **B2MML General Recipes** and matches them against **Asset Administration Shell (AAS)** resource capabilities using an SMT solver (Z3).

The tool provides a modern GUI to visualize matching solutions, optimize resource selection based on Energy/CO2/Cost, and export the final B2MML Master Recipe.

---

## 🌟 Key Features

* **Intelligent Matching**: Uses **Z3 SMT Solver** to find resources that satisfy recipe requirements (parameters, constraints, topology).
* **Three Optimization Modes**:
    * 🟢 **Fast**: Finds the first valid solution quickly.
    * 🔵 **Pro**: Finds all possible valid solutions.
    * 🟠 **Ultra**: Finds all solutions and ranks them by Energy, Use Cost, and CO2 Footprint.
* **Master Recipe Generation**: Exports the selected solution into a standardized **B2MML Master Recipe XML**.
* **Modern UI**: Built with **PyQt6-Fluent-Widgets** for a sleek, Windows 11-style interface with Dark Mode support.
* **Dynamic Configuration**: Customizable weights for optimization criteria (Energy vs Cost vs CO2).

---

## 📥 Installation

### 1. Download Executable
You do not need to install Python to use this tool.
* Go to the **[Releases](../../releases)** page.
* Download the latest **`SMT4ModPlant.exe`**.

### 2. (Optional) Download Examples
For testing, you can also download the example files provided in the repository:
* **Example General Recipes** (XML)
* **Example AAS Resources** (XML/AASX)

### 3. Run
Simply double-click `SMT4ModPlant.exe` to launch the application.

---

## 🛠️ Compilation & Development

If you want to run the source code or compile it yourself, please follow these steps.

### Prerequisites
* **Python 3.10+** is required.

### Install Dependencies
Please run the following commands in your terminal to install the required packages:

```bash
# 1. Install GUI Framework (Fluent Widgets)
pip install "PyQt6-Fluent-Widgets[full]" -i [https://pypi.org/simple/](https://pypi.org/simple/)

# 2. Install SMT Solver and Qt Bindings
pip install z3-solver PyQt6

```

### Run from Source

```bash
python gui_main.py

```

---

## 🚀 How to Use

### 1. Launch the Application

Run the downloaded `.exe` file or the python script.

### 2. Select Inputs

* **General Recipe XML**: Click `Select File` to choose your B2MML process recipe.
* **Resources Directory**: Click `Select Folder` to choose the directory containing your AAS resource descriptions (`.xml` or `.aasx` files).

### 3. Choose Optimization Mode

Use the slider to select your desired mode:

* **Fast (Green)**: Good for quick validation.
* **Pro (Blue)**: Good for exploring alternatives.
* **Ultra (Orange)**: Enables cost calculation and ranking. (Unlocks "Optimization Weights" in Settings).

### 4. Run Calculation

Click the large **Start Calculation** button. The progress bar will show the status of parsing and solving.

### 5. View & Export Results

* Once finished, the app automatically switches to the **Results** page.
* In **Ultra Mode**, results are sorted by the best score.
* Click on any row to select a solution.
* Click **Export Master Recipe** to save the generated B2MML XML file.
* *Tip: You can change the default export path in the **Settings** page.*



---

## ⚙️ Settings

* **Dark Mode**: Toggle between Light and Dark themes.
* **Export Directory**: Choose where generated XML files are saved (Default: Downloads folder).
* **Optimization Weights**: (Visible only in Ultra Mode) Adjust the importance of:
* Energy Cost
* Use Cost
* CO2 Footprint
*(Weights automatically balance to sum to 1.0)*



---

## 📝 License

[MIT License](https://en.wikipedia.org/wiki/MIT_License)
