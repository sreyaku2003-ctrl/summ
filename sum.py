from flask import Flask, request, jsonify
from groq import Groq
import PyPDF2
import docx
import io
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Get API key from environment variable
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

def extract_text_from_pdf(file):
    """Extract text from PDF file with better error handling"""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        total_pages = len(pdf_reader.pages)
        
        print(f"   Total pages: {total_pages}")
        
        # Extract text from each page
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
            except Exception as e:
                print(f"⚠️ Warning: Could not extract page {page_num + 1}: {str(e)}")
                continue
        
        if not text.strip():
            raise Exception("No text could be extracted from PDF. It might be a scanned image or corrupted.")
        
        print(f"   Extracted {len(text)} characters from {total_pages} pages")
        return text
        
    except Exception as e:
        # If PyPDF2 fails completely, raise a user-friendly error
        raise Exception(f"PDF parsing failed: {str(e)}. The PDF might be corrupted, password-protected, or image-based.")

def extract_text_from_docx(file):
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        
        if not text.strip():
            raise Exception("No text found in DOCX file")
        
        return text
    except Exception as e:
        raise Exception(f"DOCX parsing failed: {str(e)}")

def extract_text_from_txt(file):
    """Extract text from TXT file"""
    try:
        return file.read().decode('utf-8')
    except UnicodeDecodeError:
        # Try different encodings
        file.seek(0)
        try:
            return file.read().decode('latin-1')
        except:
            raise Exception("Could not decode text file. Unsupported encoding.")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Summarization & Note Making API',
        'version': '1.0'
    }), 200

@app.route('/summarize', methods=['POST'])
def summarize():
    """
    Summarize document or text
    
    Accepts:
    - file: PDF/DOCX/TXT file (optional)
    - text: Plain text (optional)
    - chapter: Chapter name/topic (optional)
    - word_count: Desired summary length (default: 300)
    
    Returns: Summary in specified word count
    """
    try:
        if not GROQ_API_KEY:
            return jsonify({'error': 'API key not configured'}), 500
        
        # Get parameters
        chapter = request.form.get('chapter', '')
        word_count = int(request.form.get('word_count', 300))
        
        # Extract text from file or use provided text
        text = ""
        
        if 'file' in request.files:
            file = request.files['file']
            filename = file.filename.lower()
            
            print(f"\n{'='*50}")
            print(f"📄 Processing File: {file.filename}")
            print(f"{'='*50}\n")
            
            try:
                # Extract text based on file type
                if filename.endswith('.pdf'):
                    text = extract_text_from_pdf(file)
                elif filename.endswith('.docx'):
                    text = extract_text_from_docx(file)
                elif filename.endswith('.txt'):
                    text = extract_text_from_txt(file)
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Unsupported file format',
                        'message': 'Please upload PDF, DOCX, or TXT file'
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'message': 'Failed to extract text from file'
                }), 400
                
        elif 'text' in request.form:
            text = request.form.get('text')
        else:
            return jsonify({
                'success': False,
                'error': 'No input provided',
                'message': 'Please provide either file or text'
            }), 400
        
        if not text.strip():
            return jsonify({
                'success': False,
                'error': 'Empty content',
                'message': 'The file or text is empty'
            }), 400
        
        # Create prompt for summarization
        # Use more text if chapter is specified (need to search through document)
        text_limit = 20000 if chapter else 8000
        text_to_use = text[:text_limit]
        
        if chapter:
            prompt = f"""You are an expert at creating educational summaries.

Text from document:
{text_to_use}

Task: Create a summary focusing on "{chapter}"

Instructions:
- Read through the entire text carefully
- Look for sections, headings, or content related to "{chapter}"
- Write a clear, concise summary in approximately {word_count} words
- If "{chapter}" content is found, summarize ONLY that section
- If "{chapter}" is not found, state that clearly and suggest what content is available
- Cover key concepts, main ideas, and important points
- Use simple, easy-to-understand language

Generate the summary now:"""
        else:
            prompt = f"""You are an expert at creating educational summaries.

Text to summarize:
{text_to_use}

Task: Create a comprehensive summary

Requirements:
- Write a clear, concise summary in approximately {word_count} words
- Cover all key concepts and main ideas
- Use simple, easy-to-understand language
- Structure: Introduction → Main Points → Conclusion

Generate the summary now:"""
        
        print(f"📝 Generating summary...")
        print(f"   Chapter: {chapter if chapter else 'Full document'}")
        print(f"   Word count: {word_count}")
        
        # Initialize Groq client
        client = Groq(api_key=GROQ_API_KEY)
        
        # Generate summary
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert educational content summarizer. Create clear, concise summaries that capture key information."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=2000,
        )
        
        summary = response.choices[0].message.content.strip()
        
        print(f"✅ Summary generated successfully!\n")
        
        return jsonify({
            'success': True,
            'summary': summary,
            'chapter': chapter if chapter else 'Full document',
            'word_count': len(summary.split())
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/create-notes', methods=['POST'])
def create_notes():
    """
    Create topic-wise notes from document
    
    Accepts:
    - file: PDF/DOCX/TXT file (optional)
    - text: Plain text (optional)
    - chapter: Chapter name (optional)
    
    Returns: Structured notes organized by topics
    """
    try:
        if not GROQ_API_KEY:
            return jsonify({'error': 'API key not configured'}), 500
        
        chapter = request.form.get('chapter', '')
        
        # Extract text
        text = ""
        
        if 'file' in request.files:
            file = request.files['file']
            filename = file.filename.lower()
            
            print(f"\n{'='*50}")
            print(f"📝 Creating Notes: {file.filename}")
            print(f"{'='*50}\n")
            
            try:
                if filename.endswith('.pdf'):
                    text = extract_text_from_pdf(file)
                elif filename.endswith('.docx'):
                    text = extract_text_from_docx(file)
                elif filename.endswith('.txt'):
                    text = extract_text_from_txt(file)
                else:
                    return jsonify({'success': False, 'error': 'Unsupported file format'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400
                
        elif 'text' in request.form:
            text = request.form.get('text')
        else:
            return jsonify({'success': False, 'error': 'No input provided'}), 400
        
        if not text.strip():
            return jsonify({'success': False, 'error': 'Empty content'}), 400
        
        # Create prompt for note-making
        # Use more text if chapter is specified
        text_limit = 20000 if chapter else 8000
        text_to_use = text[:text_limit]
        
        if chapter:
            prompt = f"""You are an expert note-maker for students.

Text from document:
{text_to_use}

Task: Create detailed, topic-wise notes focusing on "{chapter}"

Instructions:
- Read through the text carefully
- Look for sections, headings, or content related to "{chapter}"
- If "{chapter}" content is found, create notes ONLY for that section
- If "{chapter}" is not found, state that clearly
- For each topic, provide:
   - Clear heading
   - Key points (bullet points)
   - Important definitions
   - Examples if available
- Format as structured notes using markdown
- Make it student-friendly

Generate topic-wise notes now:"""
        else:
            prompt = f"""You are an expert note-maker for students.

Text:
{text_to_use}

Task: Create detailed, topic-wise notes from this content

Requirements:
1. Identify all major topics/concepts
2. For each topic, provide:
   - Clear heading
   - Key points (bullet points)
   - Important definitions
   - Examples if available
3. Format as structured notes
4. Use markdown formatting
5. Make it student-friendly

Generate topic-wise notes now:"""
        
        print(f"📚 Creating topic-wise notes...")
        print(f"   Chapter: {chapter if chapter else 'Full document'}")
        
        # Initialize Groq client
        client = Groq(api_key=GROQ_API_KEY)
        
        # Generate notes
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at creating organized, topic-wise educational notes. Make them clear, structured, and easy to study from."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=3000,
        )
        
        notes = response.choices[0].message.content.strip()
        
        print(f"✅ Notes created successfully!\n")
        
        return jsonify({
            'success': True,
            'notes': notes,
            'chapter': chapter if chapter else 'Full document'
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/summarize-and-notes', methods=['POST'])
def summarize_and_notes():
    """
    Generate both summary AND notes in one request
    
    Accepts:
    - file: PDF/DOCX/TXT file
    - chapter: Chapter name (optional)
    - word_count: Summary word count (default: 300)
    
    Returns: Both summary and topic-wise notes
    """
    try:
        if not GROQ_API_KEY:
            return jsonify({'error': 'API key not configured'}), 500
        
        chapter = request.form.get('chapter', '')
        word_count = int(request.form.get('word_count', 300))
        
        # Extract text
        text = ""
        
        if 'file' in request.files:
            file = request.files['file']
            filename = file.filename.lower()
            
            print(f"\n{'='*50}")
            print(f"📚 Processing: {file.filename}")
            print(f"{'='*50}\n")
            
            try:
                if filename.endswith('.pdf'):
                    text = extract_text_from_pdf(file)
                elif filename.endswith('.docx'):
                    text = extract_text_from_docx(file)
                elif filename.endswith('.txt'):
                    text = extract_text_from_txt(file)
                else:
                    return jsonify({'success': False, 'error': 'Unsupported file format'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400
        elif 'text' in request.form:
            text = request.form.get('text')
        else:
            return jsonify({'success': False, 'error': 'No input provided'}), 400
        
        if not text.strip():
            return jsonify({'success': False, 'error': 'Empty content'}), 400
        
        client = Groq(api_key=GROQ_API_KEY)
        
        # Use more text if chapter is specified (need to search through document)
        text_for_processing = text[:20000] if chapter else text[:8000]
        
        # Generate Summary
        print(f"📝 Generating summary ({word_count} words)...")
        
        if chapter:
            summary_prompt = f"""Text from document: {text_for_processing}

Create a {word_count}-word summary focusing on "{chapter}".
Read the text and identify content related to "{chapter}", then summarize the key concepts clearly."""
        else:
            summary_prompt = f"""Text: {text_for_processing}

Create a {word_count}-word summary covering all key concepts clearly and concisely."""
        
        summary_response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an expert summarizer."},
                {"role": "user", "content": summary_prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=2000,
        )
        
        summary = summary_response.choices[0].message.content.strip()
        
        # Generate Notes
        print(f"📚 Creating topic-wise notes...")
        
        if chapter:
            notes_prompt = f"""Text from document: {text_for_processing}

Create detailed topic-wise notes focusing on "{chapter}".
Identify content related to "{chapter}" and format as topics with bullet points, definitions, and key concepts."""
        else:
            notes_prompt = f"""Text: {text_for_processing}

Create detailed topic-wise notes.
Format: Topics with bullet points, definitions, and key concepts."""
        
        notes_response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an expert note-maker."},
                {"role": "user", "content": notes_prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=3000,
        )
        
        notes = notes_response.choices[0].message.content.strip()
        
        print(f"✅ Summary and Notes generated!\n")
        
        return jsonify({
            'success': True,
            'summary': summary,
            'notes': notes,
            'chapter': chapter if chapter else 'Full document',
            'summary_word_count': len(summary.split())
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("📚 SUMMARIZATION & NOTE MAKING API SERVER")
    print("="*60)
    
    if not GROQ_API_KEY:
        print("⚠️  WARNING: Please add your Groq API key!")
    else:
        print("✅ API Key: Configured")
    
    print("\n📡 API ENDPOINTS:")
    print("   GET  /health")
    print("        → Health check")
    print("\n   POST /summarize")
    print("        → Generate summary (300 words)")
    print("        → Body: file (PDF/DOCX/TXT), chapter (optional), word_count (optional)")
    print("\n   POST /create-notes")
    print("        → Create topic-wise notes")
    print("        → Body: file (PDF/DOCX/TXT), chapter (optional)")
    print("\n   POST /summarize-and-notes")
    print("        → Generate both summary AND notes")
    print("        → Body: file (PDF/DOCX/TXT), chapter (optional)")
    print("\n🌐 Server: http://127.0.0.1:5002")
    print("="*60 + "\n")
    
    app.run(debug=True, port=5002, host='0.0.0.0')