from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
import os
import shutil
import uuid
import time
import asyncio
from typing import List, Dict, Any, Optional
import base64
from io import BytesIO
from PIL import Image
import json
import subprocess
import platform
from pathlib import Path
import hashlib
from datetime import datetime, timedelta
import pandas as pd
import re
from pydantic import BaseModel
import google.generativeai as genai
import traceback
from openpyxl import load_workbook
from contextlib import asynccontextmanager
from hindsight_manager import get_hindsight_manager, HindsightManager

# Configuration
GEMINI_API_KEY = "AIzaSyCQ5IbXH0WnqBdaoEBY-o5w87OgDZ3V5NU"

# Global storage for proposals and image cache
proposals = {}
image_cache = {}
conversion_status = {}  # Track conversion progress

# Initialize Hindsight for memory
hindsight_manager = None

# Initialize Gemini configuration
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    print("\n" + "="*60)
    print("🚀 Server Starting Up...")
    print("="*60)
    
    # Initialize Hindsight memory system
    global hindsight_manager
    hindsight_manager = get_hindsight_manager()
    status = hindsight_manager.get_status()
    if status["connected"]:
        print("✅ Hindsight Memory System Initialized")
        print(f"   Memory Bank: {status['bank_name']}")
    else:
        print("⚠️  Hindsight not available (optional)")
    
    # Generate template images on startup
    generate_template_images_on_startup()
    
    print("="*60)
    print("✅ Server ready to accept requests")
    print("="*60 + "\n")
    
    yield
    
    # Shutdown (optional cleanup)
    print("\n👋 Server shutting down...")

# Initialize FastAPI with lifespan
app = FastAPI(lifespan=lifespan)

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("temp", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("slide_images", exist_ok=True)
os.makedirs("generated_proposals", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/slide_images", StaticFiles(directory="slide_images"), name="slide_images")
app.mount("/generated_proposals", StaticFiles(directory="generated_proposals"), name="generated_proposals")

class UpdateRequest(BaseModel):
    changes: str

def get_file_hash(file_path: str) -> str:
    """Generate a hash for a file to detect changes"""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def clear_slide_images_folder():
    """Clear all images from the slide_images folder"""
    try:
        for file in os.listdir("slide_images"):
            if file.endswith('.png'):
                file_path = os.path.join("slide_images", file)
                os.remove(file_path)
                print(f"🗑️  Deleted: {file}")
        print("✅ Slide images folder cleared")
    except Exception as e:
        print(f"❌ Error clearing slide images folder: {e}")

def cleanup_old_images(keep_pattern: str = None):
    """Clean up old slide images, keeping only the specified pattern"""
    try:
        for file in os.listdir("slide_images"):
            if file.endswith('.png'):
                if keep_pattern and file.startswith(keep_pattern):
                    continue
                
                file_path = os.path.join("slide_images", file)
                file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_age > timedelta(hours=1):
                    os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up images: {e}")

class DiscoveryDocumentProcessor:
    """Process and extract information from discovery documents"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = {}
        
    def process(self) -> Dict[str, Any]:
        """Process the discovery document and extract key information"""
        try:
            # Read Excel file
            if self.file_path.endswith('.xlsx'):
                workbook = load_workbook(self.file_path, data_only=True)
                self.data = self._extract_from_xlsx(workbook)
            else:
                # Use pandas for .xls files
                excel_data = pd.read_excel(self.file_path, sheet_name=None)
                self.data = self._extract_from_xls(excel_data)
            
            return self.data
            
        except Exception as e:
            print(f"Error processing discovery document: {e}")
            return {}
    
    def _extract_from_xlsx(self, workbook) -> Dict[str, Any]:
        """Extract data from .xlsx file"""
        extracted_data = {}
        
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            sheet_data = []
            
            # Get headers
            headers = []
            for cell in sheet[1]:
                if cell.value:
                    headers.append(str(cell.value))
            
            # Get data rows
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if any(row):  # Skip empty rows
                    row_dict = {}
                    for idx, value in enumerate(row):
                        if idx < len(headers) and value is not None:
                            row_dict[headers[idx]] = str(value)
                    if row_dict:
                        sheet_data.append(row_dict)
            
            extracted_data[sheet_name] = {
                "headers": headers,
                "data": sheet_data
            }
        
        return extracted_data
    
    def _extract_from_xls(self, excel_data) -> Dict[str, Any]:
        """Extract data from .xls file using pandas"""
        extracted_data = {}
        
        for sheet_name, df in excel_data.items():
            # Convert DataFrame to dictionary format
            sheet_data = df.where(pd.notnull(df), None).to_dict('records')
            
            # Clean up the data
            cleaned_data = []
            for row in sheet_data:
                cleaned_row = {}
                for key, value in row.items():
                    if value is not None:
                        cleaned_row[str(key)] = str(value)
                if cleaned_row:
                    cleaned_data.append(cleaned_row)
            
            extracted_data[sheet_name] = {
                "headers": list(df.columns),
                "data": cleaned_data
            }
        
        return extracted_data

class GeminiContentGenerator:
    """Generate content for PPT placeholders using Gemini API"""
    
    def __init__(self):
        self.model = gemini_model
        self.max_retries = 3

        # Mapped specifically to your template.pptx structure
        self.SLIDE_GUIDELINES = {
            "1": """**Slide 1 (Cover):**
                    - {{COVER TITLE}}: Insert a professional proposal title (e.g., 'Strategic Growth Proposal for [Client Name from document]').
                    - {{DATE}}: Insert the current date.""",
            
            "2": """**Slide 2 (Cover Letter):**
                    - {{COVER_LETTER}}: Write a 150–200 word welcome letter. Introduce the proposal, express excitement, 
                    reaffirm alignment with client vision, and emphasize 'Pnyxhill' as a strategic partner. 
                    Close with 'Sincerely, [Your Name]'.""",
            
            "3": """**Slide 3 (Executive Summary):**
                    - {{EXECUTIVE_SUMMARY}}: Create a comprehensive summary. 
                    Structure it with bold headers: 
                    1. **Growth Ambition** (Intro)
                    2. **Our Value Proposition** (3-4 bullets)
                    3. **Key Project Highlights** (6-8 service modules)
                    4. **Strategic Outlook** (Closing sentence).""",
            
            "13": """**Slide 13 (Understanding & POV):**
                     - {{CURRENT SITUATION OF CLIENT}}: Describe market context and unmet needs based on research.
                     - {{KEY CHALLENGES}}: List 4-6 strategic hurdles with short headers.
                     - {{OUTCOMES REQUIRED}}: Define 4-5 tangible results the client aims to achieve.""",
            
            "14": """**Slide 14 (Proposed Approach):**
                     - {{Introductory Paragraph}}: 2-3 sentences on the phased, insight-led approach.
                     - {{Phase 1: Name}}, {{Phase 2: Name}}, {{Phase 3: Name}}: Provide short, punchy titles for 3 distinct phases.
                     - {{Phase 1 Points}}, {{Phase 2 Points}}, {{Phase 3 Points}}: For EACH phase, provide 3-4 concise bullet points describing activities/deliverables.""",
            
            "16": """**Slide 16 (Scope of Services):**
                     - {{strategic support}}: 3-4 bullets on strategic advisory services. Format: '<Title>: <Explanation>'
                     - {{structuring & enablers}}: 3-4 bullets on operational/structuring services.
                     - {{ongoing support}}: 3-4 bullets on long-term execution/advisory support.""",
            
            "17": """**Slide 17 (Deliverables - Part 1):**
                     - {{TITLE OF SERVICE DELIVERABLES 1}}: Title for the first service category.
                     - {{Points for Service Deliverables 1}}: 3-4 action-oriented bullet points.
                     - {{TITLE OF SERVICE DELIVERABLES 2}}: Title for the second service category.
                     - {{Points for Service Deliverables 2}}: 3-4 action-oriented bullet points.""",
            
            "18": """**Slide 18 (Deliverables - Part 2):**
                     - {{TITLE OF SERVICE DELIVERABLES 3}}: Title for the third service category (different from Slide 17).
                     - {{Points for Service Deliverables 3}}: 3-4 action-oriented bullet points.
                     - {{TITLE OF SERVICE DELIVERABLES 4}}: Title for the fourth service category.
                     - {{Points for Service Deliverables 4}}: 3-4 action-oriented bullet points."""
        }    

    def generate_content(self, placeholders: Dict[str, List[str]], discovery_data: Dict[str, Any], hindsight_context: str = "") -> Dict[str, Any]:
        """Generate content for all placeholders based on discovery document with retry logic"""
        
        # Prepare the prompt
        prompt = self._create_prompt(placeholders, discovery_data, hindsight_context)
        
        for attempt in range(self.max_retries):
            try:
                print(f"🤖 Attempting Gemini API call (attempt {attempt + 1}/{self.max_retries})...")
                
                # Generate content using Gemini
                response = self.model.generate_content(prompt)
                
                # Parse the response
                content = self._parse_response(response.text)
                
                print(f"✅ Gemini API call successful!")
                return content
                
            except Exception as e:
                error_msg = str(e)
                print(f"⚠️  Attempt {attempt + 1} failed: {error_msg}")
                
                # If this is not the last attempt, wait before retrying
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    # Last attempt failed
                    print(f"❌ All {self.max_retries} attempts failed. Using default content.")
                    traceback.print_exc()
        
        # If all retries fail, return default content
        return self._get_default_content(placeholders)
    
    def _create_prompt(self, placeholders: Dict[str, List[str]], discovery_data: Dict[str, Any], hindsight_context: str = "") -> str:
        """Create a detailed prompt for Gemini"""
        
        discovery_text = json.dumps(discovery_data, indent=2)
        
        # Build context string
        slides_context = ""
        for slide_key, slide_placeholders in placeholders.items():
            # Extract slide number (e.g., "slide_13" -> "13")
            slide_num = slide_key.replace("slide_", "")
            
            slides_context += f"\n--- SLIDE {slide_num} ---\n"
            
            # Inject specific guidelines if available for this slide
            if slide_num in self.SLIDE_GUIDELINES:
                slides_context += f"🔴 GUIDELINE: {self.SLIDE_GUIDELINES[slide_num]}\n"
            else:
                slides_context += "GUIDELINE: Generate professional content fitting the placeholder names.\n"
            
            slides_context += "PLACEHOLDERS TO FILL:\n"
            for ph in slide_placeholders:
                slides_context += f"  - {ph}\n"
        
        # Add hindsight context if available
        hindsight_section = ""
        if hindsight_context.strip():
            hindsight_section = f"""
**RELEVANT PAST PROPOSALS & PATTERNS (from memory):**
{hindsight_context}

Consider these patterns and user preferences when generating content. Apply similar successful approaches where applicable.
"""
        
        prompt = f"""
You are a Senior Strategy Consultant at 'Pnyx Hill'. You are writing a business proposal.

**INPUT DATA (Discovery Document):**
{discovery_text}
{hindsight_section}

**INSTRUCTIONS:**
1. Analyze the **GUIDELINES** for each slide below carefully.
2. Map your generated content strictly to the **PLACEHOLDERS** listed.
3. **Tone:** Top-tier management consulting (McKinsey/BCG style). Professional, insightful, and direct.
4. **Formatting:** Use bullet points (•) within the text where appropriate. Do not use markdown (#, **) inside the JSON values unless requested.

**SLIDE REQUESTS:**
{slides_context}

**OUTPUT FORMAT:**
Return ONLY a valid JSON object with this exact structure:
{{
    "slide_1": {{
        "{{COVER TITLE}}": "Generated Title Here",
        "{{DATE}}": "Generated Date Here"
    }},
    "slide_13": {{
        "{{CURRENT SITUATION OF CLIENT}}": "Content..."
    }}
}}

Do not include any markdown code blocks (like ```json). Just the raw JSON string.
"""
        return prompt
        
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the Gemini response into structured content"""
        try:
            # Remove markdown code blocks if present
            response_text = response_text.strip()
            if response_text.startswith('```'):
                response_text = re.sub(r'^```(?:json)?\s*\n', '', response_text)
                response_text = re.sub(r'\n```\s*$', '', response_text)
            
            # Parse JSON
            content = json.loads(response_text)
            return content
            
        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini response: {e}")
            print(f"Response text: {response_text[:500]}...")
            return {}
    
    def _get_default_content(self, placeholders: Dict[str, List[str]]) -> Dict[str, Any]:
        """Generate default content if AI generation fails"""
        default_content = {}
        
        for slide_num, slide_placeholders in placeholders.items():
            default_content[slide_num] = {}
            for placeholder in slide_placeholders:
                default_content[slide_num][placeholder] = f"[Content for {placeholder}]"
        
        return default_content
    
class PPTXProcessor:
    """Enhanced processor for PPTX files with image generation capabilities"""
    
    def __init__(self, pptx_path: str):
        self.pptx_path = pptx_path
        self.presentation = Presentation(pptx_path)
        self.slides_data = []
        
    def extract_placeholders(self) -> Dict[str, List[str]]:
        """Extract all placeholders from the presentation"""
        placeholders = {}
        
        for slide_idx, slide in enumerate(self.presentation.slides, 1):
            slide_placeholders = []
            
            for shape in slide.shapes:
                if shape.has_text_frame:
                    # Check for placeholders in text
                    text = shape.text_frame.text
                    # Find all {{placeholder}} patterns
                    found_placeholders = re.findall(r'\{\{([^}]+)\}\}', text)
                    slide_placeholders.extend(found_placeholders)
            
            if slide_placeholders: 
                placeholders[f"slide_{slide_idx}"] = list(set(slide_placeholders))  # Remove duplicates
        
        return placeholders
    
    def replace_placeholders(self, content: Dict[str, Any]) -> bool:
        """Replace placeholders in the presentation with generated content"""
        try:
            for slide_idx, slide in enumerate(self.presentation.slides, 1):
                slide_key = f"slide_{slide_idx}"
                
                if slide_key not in content:
                    continue
                
                slide_content = content[slide_key]
                
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        # Replace placeholders in the text
                        text_frame = shape.text_frame
                        original_text = text_frame.text
                        
                        for placeholder, replacement in slide_content.items():
                            pattern = f"{{{{{placeholder}}}}}"
                            if pattern in original_text:
                                # Clear existing text
                                text_frame.clear()
                                
                                # Add new paragraph with proper formatting
                                p = text_frame.paragraphs[0]
                                
                                # Handle bullet points
                                if isinstance(replacement, list):
                                    for item in replacement:
                                        if p.text:  # If paragraph already has content
                                            p = text_frame.add_paragraph()
                                        p.text = str(item)
                                        p.level = 0
                                else:
                                    p.text = str(replacement)
                                
                                original_text = original_text.replace(pattern, str(replacement))
            
            return True
            
        except Exception as e:
            print(f"Error replacing placeholders: {e}")
            traceback.print_exc()
            return False
    
    def save_presentation(self, output_path: str):
        """Save the modified presentation"""
        self.presentation.save(output_path)
    
    def convert_to_images(self, prefix: str = "slide", force_regenerate: bool = False) -> List[Dict[str, Any]]:
        """
        Convert all slides to images IN BATCH (no incremental reloading)
        Images are stored in the slide_images folder with simple filenames: slide_1.png, slide_2.png, etc.
        """
        slides_data = []
        
        # Check if images already exist (unless force_regenerate is True)
        first_slide_path = os.path.join("slide_images", "slide_1.png")
        if os.path.exists(first_slide_path) and not force_regenerate:
            print("📸 Loading existing slide images from cache...")
            # Load existing images
            for slide_idx in range(1, len(self.presentation.slides) + 1):
                image_filename = f"slide_{slide_idx}.png"
                image_path = os.path.join("slide_images", image_filename)
                
                if os.path.exists(image_path):
                    slides_data.append({
                        "slide_number": slide_idx,
                        "title": self._get_slide_title(self.presentation.slides[slide_idx - 1]),
                        "image_url": f"/slide_images/{image_filename}",
                        "text_content": self._get_slide_text(self.presentation.slides[slide_idx - 1])
                    })
            return slides_data
        
        try:
            print(f"📄 Converting PowerPoint to images (BATCH MODE)...")
            
            system = platform.system()
            
            if system == "Windows":
                slides_data = self._convert_windows()
            elif system == "Darwin":  # macOS
                slides_data = self._convert_macos()
            else:  # Linux
                slides_data = self._convert_linux()
            
            print(f"✅ Generated {len(slides_data)} slide images (ALL AT ONCE)")
            return slides_data
            
        except Exception as e:
            print(f"❌ Error converting slides to images: {e}")
            traceback.print_exc()
            # Return slide data without images as fallback
            return self._get_slides_without_images()
    
    def _convert_windows(self) -> List[Dict[str, Any]]:
        """Convert PowerPoint to images on Windows using comtypes - BATCH MODE"""
        slides_data = []
        
        try:
            import comtypes.client
            
            # Get absolute path
            abs_pptx_path = os.path.abspath(self.pptx_path)
            abs_output_dir = os.path.abspath("slide_images")
            
            # Initialize PowerPoint
            powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
            powerpoint.Visible = 1
            
            # Open presentation
            presentation = powerpoint.Presentations.Open(abs_pptx_path)
            
            print(f"🔄 Converting {len(presentation.Slides)} slides to images...")
            
            # Export ALL slides as PNG (batch operation)
            for slide_idx, slide in enumerate(presentation.Slides, 1):
                output_filename = f"slide_{slide_idx}.png"
                output_path = os.path.join(abs_output_dir, output_filename)
                
                # Export slide as PNG
                slide.Export(output_path, "PNG", 1280, 720)
                
                slides_data.append({
                    "slide_number": slide_idx,
                    "title": self._get_slide_title(self.presentation.slides[slide_idx - 1]),
                    "image_url": f"/slide_images/{output_filename}",
                    "text_content": self._get_slide_text(self.presentation.slides[slide_idx - 1])
                })
            
            # Close presentation and quit PowerPoint
            presentation.Close()
            powerpoint.Quit()
            
            print(f"✅ All {len(slides_data)} slides converted successfully")
            
        except ImportError:
            print("⚠️  comtypes not available, using LibreOffice fallback")
            slides_data = self._convert_libreoffice()
        except Exception as e:
            print(f"Error in Windows conversion: {e}")
            traceback.print_exc()
            slides_data = self._convert_libreoffice()
        
        return slides_data
    
    def _convert_macos(self) -> List[Dict[str, Any]]:
        """Convert PowerPoint to images on macOS"""
        return self._convert_libreoffice()
    
    def _convert_linux(self) -> List[Dict[str, Any]]:
        """Convert PowerPoint to images on Linux"""
        return self._convert_libreoffice()
    
    def _convert_libreoffice(self) -> List[Dict[str, Any]]:
        """Convert PowerPoint to images using LibreOffice - BATCH MODE"""
        slides_data = []
        
        try:
            # Find LibreOffice command
            libreoffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
            
            if not libreoffice_cmd:
                print("⚠️  LibreOffice not found")
                return self._get_slides_without_images()
            
            # Create temp directory for PDF
            temp_pdf_dir = "temp/pdf_conversion"
            os.makedirs(temp_pdf_dir, exist_ok=True)
            
            # Convert PPTX to PDF (single operation)
            abs_pptx_path = os.path.abspath(self.pptx_path)
            
            print("🔄 Converting PPTX to PDF...")
            subprocess.run([
                libreoffice_cmd,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", temp_pdf_dir,
                abs_pptx_path
            ], check=True, capture_output=True)
            
            # Find the generated PDF
            pdf_filename = os.path.splitext(os.path.basename(self.pptx_path))[0] + ".pdf"
            pdf_path = os.path.join(temp_pdf_dir, pdf_filename)
            
            if not os.path.exists(pdf_path):
                print(f"⚠️  PDF not generated at {pdf_path}")
                return self._get_slides_without_images()
            
            # Convert PDF to images (batch operation - ALL AT ONCE)
            from pdf2image import convert_from_path
            
            print("🔄 Converting PDF to images...")
            images = convert_from_path(pdf_path, dpi=150)
            
            print(f"💾 Saving {len(images)} images to disk...")
            # Save ALL images (batch operation)
            for slide_idx, image in enumerate(images, 1):
                output_filename = f"slide_{slide_idx}.png"
                output_path = os.path.join("slide_images", output_filename)
                image.save(output_path, "PNG")
                
                slides_data.append({
                    "slide_number": slide_idx,
                    "title": self._get_slide_title(self.presentation.slides[slide_idx - 1]),
                    "image_url": f"/slide_images/{output_filename}",
                    "text_content": self._get_slide_text(self.presentation.slides[slide_idx - 1])
                })
            
            # Cleanup
            shutil.rmtree(temp_pdf_dir)
            
            print(f"✅ All {len(slides_data)} slides saved successfully")
            
        except Exception as e:
            print(f"Error in LibreOffice conversion: {e}")
            traceback.print_exc()
            return self._get_slides_without_images()
        
        return slides_data
    
    def _get_slide_title(self, slide) -> str:
        """Extract title from a slide"""
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                return shape.text.split('\n')[0][:50]
        return f"Slide"
    
    def _get_slide_text(self, slide) -> List[str]:
        """Extract all text content from a slide"""
        text_content = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                text_content.append(shape.text)
        return text_content
    
    def _get_slides_without_images(self) -> List[Dict[str, Any]]:
        """Return slide data without images (fallback)"""
        slides_data = []
        for slide_idx, slide in enumerate(self.presentation.slides, 1):
            slides_data.append({
                "slide_number": slide_idx,
                "title": self._get_slide_title(slide),
                "image_url": None,
                "text_content": self._get_slide_text(slide)
            })
        return slides_data

def generate_template_images_on_startup():
    """
    Generate template slide images on server startup
    This ensures images are always available in the slide_images folder
    """
    template_path = "template.pptx"
    
    if not os.path.exists(template_path):
        print("⚠️  Warning: template.pptx not found. Please add a template file.")
        return
    
    print("🚀 Generating template slide images on startup...")
    
    try:
        # Clear existing images first
        clear_slide_images_folder()
        
        # Generate new template images (BATCH MODE)
        processor = PPTXProcessor(template_path)
        slides_data = processor.convert_to_images(prefix="template", force_regenerate=True)
        
        print(f"✅ Successfully generated {len(slides_data)} template slide images")
        print(f"📁 Images stored in: {os.path.abspath('slide_images')}")
        
    except Exception as e:
        print(f"❌ Error generating template images: {e}")
        traceback.print_exc()

# FastAPI event handlers
@app.get("/")
async def root():
    return {"message": "PPT Proposal Builder API with AI Content Generation"}

@app.get("/api/template/slides")
async def get_template_slides():
    """
    Get all slides from the slide_images folder
    This endpoint loads whatever images are currently in the folder
    (template images initially, proposal images after generation)
    """
    try:
        slides_data = []
        
        # Get all PNG files in the slide_images folder
        slide_files = sorted([f for f in os.listdir("slide_images") if f.endswith('.png')])
        
        if not slide_files:
            return {
                "status": "error",
                "message": "No slide images found",
                "total_slides": 0,
                "slides": []
            }
        
        # Create slide data for each image
        for idx, filename in enumerate(slide_files, 1):
            slides_data.append({
                "slide_number": idx,
                "title": f"Slide {idx}",
                "image_url": f"/slide_images/{filename}",
                "text_content": []
            })
        
        return {
            "status": "success",
            "template_file": "slide_images",
            "total_slides": len(slides_data),
            "slides": slides_data
        }
        
    except Exception as e:
        print(f"Error loading slide images: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error loading slides: {str(e)}")

@app.post("/api/proposals/create")
async def create_proposal(discovery_doc: UploadFile = File(...)):
    """Create a new proposal from a discovery document - NO INCREMENTAL LOADING"""
    
    try:
        # Clear previous slide images when a new document is uploaded
        print("\n" + "="*60)
        print("📤 New discovery document uploaded")
        print("🗑️  Clearing previous slide images...")
        clear_slide_images_folder()
        print("="*60 + "\n")
        
        # Generate unique ID for this proposal
        proposal_id = str(uuid.uuid4())
        
        # Save uploaded file
        upload_path = f"uploads/discovery_{proposal_id}.xlsx"
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(discovery_doc.file, buffer)
        
        # Process discovery document
        doc_processor = DiscoveryDocumentProcessor(upload_path)
        discovery_data = doc_processor.process()
        
        # Load template
        template_path = "template.pptx"
        if not os.path.exists(template_path):
            raise HTTPException(status_code=404, detail="Template file not found")
        
        # Copy template to create proposal
        output_pptx = f"generated_proposals/proposal_{proposal_id}.pptx"
        # output_pptx = os.path.join("docs\\hyke-template.pptx")
        shutil.copy(template_path, output_pptx)
        
        # Extract placeholders from template
        proposal_processor = PPTXProcessor(output_pptx)
        placeholders = proposal_processor.extract_placeholders()
        
        print(f"Found {sum(len(p) for p in placeholders.values())} placeholders across {len(placeholders)} slides")
        
        # Recall similar proposals from Hindsight memory
        hindsight_context = ""
        if hindsight_manager:
            print("\n🧠 Querying memory for similar proposals...")
            similar_proposals = hindsight_manager.recall_similar_proposals(discovery_data, limit=3)
            user_prefs = hindsight_manager.recall_user_preferences(limit=2)
            
            if similar_proposals or user_prefs:
                hindsight_context = "Similar past proposals:\n"
                for prop in similar_proposals:
                    hindsight_context += f"  - {prop}\n"
                
                if user_prefs:
                    hindsight_context += "\nUser preferences from past refinements:\n"
                    for pref in user_prefs:
                        hindsight_context += f"  - {pref}\n"
                print(f"✅ Found relevant memory context")
        
        # Generate content using Gemini with Hindsight context
        content_generator = GeminiContentGenerator()
        generated_content = content_generator.generate_content(placeholders, discovery_data, hindsight_context)
        
        # Replace placeholders with generated content
        proposal_processor.replace_placeholders(generated_content)
        proposal_processor.save_presentation(output_pptx)
        
        print(f"✅ Proposal saved to: {output_pptx}")
        
        # Generate slide images for the NEW proposal (BATCH - ALL AT ONCE)
        print("📸 Generating slide images for proposal (BATCH MODE)...")
        # processor_for_preview = PPTXProcessor(output_pptx)
        processor_for_preview = PPTXProcessor("docs\\Pnyx Hill Strategy - Hyke Proposal - Confidential - Template.pptx")
        slides_data = processor_for_preview.convert_to_images(force_regenerate=True)
        print(f"✅ Generated {len(slides_data)} slide images for proposal (ALL COMPLETED)")

        # Store proposal information
        proposals[proposal_id] = {
            "id": proposal_id,
            "discovery_doc": upload_path,
            "proposal_file": output_pptx,
            "template_file": template_path,
            "placeholders": placeholders,
            "generated_content": generated_content,
            "discovery_data": discovery_data,
            "status": "created",
            "created_at": datetime.now().isoformat()
        }
        
        # Retain the proposal in Hindsight memory
        if hindsight_manager:
            hindsight_manager.retain_proposal({
                "proposal_id": proposal_id,
                "discovery_data": discovery_data,
                "generated_content": generated_content,
                "created_at": datetime.now().isoformat()
            })
        
        return {
            "status": "success",
            "proposal_id": proposal_id,
            "message": "Proposal created successfully",
            "placeholders_found": sum(len(p) for p in placeholders.values()),
            "content_generated": bool(generated_content),
            "slides": slides_data,
            "ppt_path": output_pptx
        }

        
    except Exception as e:
        print(f"Error creating proposal: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Error creating proposal: {str(e)}"
        )

@app.get("/api/proposals/{proposal_id}/slides")
async def get_proposal_slides(proposal_id: str):
    """
    Get all slides for a specific proposal
    This now simply returns the images from the slide_images folder
    """
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    try:
        slides_data = []
        
        # Get all PNG files in the slide_images folder
        slide_files = sorted([f for f in os.listdir("slide_images") if f.endswith('.png')])
        
        # Create slide data for each image
        for idx, filename in enumerate(slide_files, 1):
            slides_data.append({
                "slide_number": idx,
                "title": f"Slide {idx}",
                "image_url": f"/slide_images/{filename}",
                "text_content": []
            })
        
        return {
            "status": "success",
            "proposal_id": proposal_id,
            "total_slides": len(slides_data),
            "slides": slides_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing proposal: {str(e)}")

@app.post("/api/proposals/{proposal_id}/update")
async def update_proposal(proposal_id: str, update_request: UpdateRequest):
    """Update proposal content based on user input"""
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    proposal = proposals[proposal_id]
    
    try:
        print("\n" + "="*60)
        print("🔄 Updating proposal...")
        print("🗑️  Clearing previous slide images...")
        clear_slide_images_folder()
        print("="*60 + "\n")
        
        # Create a prompt for Gemini to understand the changes
        update_prompt = f"""
        You are updating a business proposal presentation. The user has requested the following changes:
        
        {update_request.changes}
        
        Current content in the presentation:
        {json.dumps(proposal['generated_content'], indent=2)}
        
        Based on the user's requested changes, provide updated content for the relevant placeholders.
        Return ONLY a valid JSON object with the same structure as the current content, but with the requested changes applied.
        Only include the slides and placeholders that need to be updated.
        
        Keep the same JSON structure:
        {{
            "slide_X": {{
                "placeholder_name": "updated content here"
            }}
        }}
        """
        
        # Generate updated content using Gemini
        response = gemini_model.generate_content(update_prompt)
        
        # Parse the response
        content_generator = GeminiContentGenerator()
        updated_content = content_generator._parse_response(response.text)
        
        # Merge updated content with existing content
        merged_content = proposal['generated_content'].copy()
        for slide_key, slide_content in updated_content.items():
            if slide_key in merged_content:
                merged_content[slide_key].update(slide_content)
            else:
                merged_content[slide_key] = slide_content
        
        # Apply updates to the presentation
        processor = PPTXProcessor(proposal["proposal_file"])
        processor.replace_placeholders(merged_content)
        processor.save_presentation(proposal["proposal_file"])
        
        # Generate NEW slide images after update (BATCH MODE)
        print("📸 Generating updated slide images (BATCH MODE)...")
        slides_data = processor.convert_to_images(force_regenerate=True)
        print(f"✅ Generated {len(slides_data)} updated slide images (ALL COMPLETED)")
        
        # Update stored proposal information
        proposal['generated_content'] = merged_content
        proposal['last_updated'] = datetime.now().isoformat()
        proposal['update_history'] = proposal.get('update_history', [])
        proposal['update_history'].append({
            'timestamp': datetime.now().isoformat(),
            'changes_requested': update_request.changes,
            'content_updated': updated_content
        })
        
        # Retain the refinements in Hindsight memory
        if hindsight_manager:
            hindsight_manager.retain_refinements(
                proposal_id=proposal_id,
                refinements=update_request.changes,
                original_content=proposal.get('generated_content', {})
            )
        
        return {
            "status": "success",
            "message": "Proposal updated successfully",
            "updated_slides": list(updated_content.keys())
        }
    
    except Exception as e:
        print(f"Error updating proposal: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating proposal: {str(e)}")

@app.get("/api/proposals/{proposal_id}/download")
async def download_proposal(proposal_id: str):
    """Download the generated proposal with file system fallback"""
    
    # 1. Try to get path from memory
    if proposal_id in proposals:
        file_path = proposals[proposal_id]["proposal_file"]
    else:
        # 2. Fallback: Check file system directly
        # We know the structure is generated_proposals/proposal_{id}.pptx
        file_path = os.path.join("generated_proposals", f"proposal_{proposal_id}.pptx")
    
    # Check if file actually exists on disk
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Proposal file not found on server")
    
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"proposal_{proposal_id}.pptx"
    )

@app.get("/api/proposals/{proposal_id}/content")
async def get_proposal_content(proposal_id: str):
    """Get the generated content for a proposal"""
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    proposal = proposals[proposal_id]
    
    return {
        "status": "success",
        "proposal_id": proposal_id,
        "placeholders": proposal.get("placeholders", {}),
        "generated_content": proposal.get("generated_content", {}),
        "discovery_data_summary": {
            sheet: {
                "headers": data["headers"],
                "row_count": len(data["data"])
            }
            for sheet, data in proposal.get("discovery_data", {}).items()
        }
    }

@app.get("/api/system/info")
async def get_system_info():
    """Get system information for debugging"""
    return {
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "gemini_configured": bool(GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"),
        "available_converters": {
            "comtypes": platform.system() == "Windows",
            "libreoffice": shutil.which("libreoffice") is not None or shutil.which("soffice") is not None,
            "pdf2image": True
        },
        "slide_images_count": len([f for f in os.listdir("slide_images") if f.endswith('.png')])
    }

if __name__ == "__main__":
    print("\n=== Enhanced PPT Backend Server with Gemini AI ===")
    print(f"Platform: {platform.system()}")
    print(f"Slide images will be saved to: {os.path.abspath('slide_images')}")
    
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\n⚠️  WARNING: Gemini API key not configured!")
        print("Please set your API key in the GEMINI_API_KEY variable or environment variable")
    else:
        print("✅ Gemini API configured")
    
    print("\nStarting server on http://localhost:8000")
    print("API docs available at http://localhost:8000/docs\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)