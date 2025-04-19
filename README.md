# Course PDF Generator

A web application for generating professional course PDFs with customizable overlays and rich text content.

## Features

- **Builder Interface** (`/ui/index.html`)
  - Rich text editor for course content
  - Pre-defined text snippets for quick insertion
  - Build PDFs with a single click
  - View and download generated artifacts

- **Overlay Designer** (`/ui/designer.html`)
  - Visual drag-and-drop interface for positioning metadata fields
  - Support for multiple text fields (title, credits, dates, etc.)
  - Customizable font sizes
  - Live PDF preview

## Setup

1. Create and activate a Python virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start the FastAPI server:
```bash
uvicorn api.main:app --reload --port 8003
```

## Usage

1. Open the Builder interface at `http://localhost:8003/ui/index.html`
   - Enter course content using the rich text editor
   - Save front matter and metadata

2. Use the Overlay Designer at `http://localhost:8003/ui/designer.html`
   - Load the source PDF
   - Drag text boxes to desired positions
   - Adjust font sizes as needed
   - Save the overlay configuration

3. Return to the Builder to generate final PDFs
   - Click "Build Course PDFs"
   - Download the generated artifacts

## Project Structure

- `/api` - FastAPI backend code
- `/courses` - Course data and generated PDFs
- `/frontend` - HTML/JavaScript UI files
- `/scripts` - PDF generation and overlay scripts
- `/templates` - HTML templates for PDF generation

## Dependencies

- FastAPI - Web framework
- PyPDF - PDF manipulation
- ReportLab - PDF generation
- TinyMCE - Rich text editing
- PDF.js - PDF viewing and overlay design 