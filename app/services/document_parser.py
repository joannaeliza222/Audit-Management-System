import os
import re
import uuid
import hashlib
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import fitz  # PyMuPDF
import pandas as pd
from werkzeug.utils import secure_filename
from flask import current_app

from app import db
from app.audit_models import DocumentProcessing, ExtractedItem
from app.utils.embeddings import get_bert_embeddings


class DocumentParser:
    """Local document parsing service for PDF, Excel, and CSV files with Q&A extraction"""
    
    def __init__(self):
        self.qa_patterns = [
            # Question patterns
            r'(?:^|\n)\s*(?:Q\d*[\.\:]?\s*|Question\s*\d*[\.\:]?\s*)(.+?)(?=\n\s*(?:A\d*[\.\:]?|Answer|\n|$))',
            r'(?:^|\n)\s*(?:\d+\.\s*|\d+\)\s*)(.+?)(?=\n\s*(?:\d+\.\s*|\d+\)\s*|\n|$))',
            r'(?:^|\n)\s*[Qq][\.\:]?\s*(.+?)(?=\n\s*[Aa][\.\:]?|\n|$))',
            
            # Answer patterns  
            r'(?:^|\n)\s*(?:A\d*[\.\:]?\s*|Answer\s*\d*[\.\:]?\s*)(.+?)(?=\n\s*(?:Q\d*[\.\:]?|Question|\n|$))',
            r'(?:^|\n)\s*[Aa][\.\:]?\s*(.+?)(?=\n\s*(?:Q\d*[\.\:]?|\n|$))',
        ]
        
        self.commitment_patterns = [
            r"will be rectified in (?:the )?(?:next|upcoming|future) (?:version|release|update)",
            r"\bwill be addressed in (?:the )?(?:next|upcoming|future) (?:version|release|update)\b",
            r"\bwill be seen in (?:the )?(?:next|upcoming|future) (?:version|release|update)\b",
            r"\bplanned for (?:the )?(?:next|upcoming|future) (?:release|version|update)\b",
            r"\bto be fixed in (?:the )?(?:next|upcoming|future) (?:release|version|update)\b",
            r"\b(?:in|on) the next release\b",
            r"\b(next|upcoming|future) (?:release|version|update)\b",
            r"\bwill be implemented\b",
            r"\bwill be rectified\b",
            r"\bfuture enhancement\b",
        ]
    
    def calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum of file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def create_document_record(self, file_storage, uploaded_by: str) -> DocumentProcessing:
        """Create document processing record"""
        original_filename = secure_filename(file_storage.filename)
        uid = uuid.uuid4().hex
        stored_filename = f"{uid}_{original_filename}"
        
        upload_folder = current_app.config['UPLOAD_FOLDER']
        file_path = os.path.join(upload_folder, stored_filename)
        
        # Save file
        file_storage.save(file_path)
        
        # Get file info
        file_size = os.path.getsize(file_path)
        file_type = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'unknown'
        checksum = self.calculate_checksum(file_path)
        
        # Determine MIME type
        mime_types = {
            'pdf': 'application/pdf',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel',
            'csv': 'text/csv'
        }
        mime_type = mime_types.get(file_type, 'application/octet-stream')
        
        # Create record
        doc = DocumentProcessing(
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            mime_type=mime_type,
            checksum=checksum,
            uploaded_by=uploaded_by
        )
        
        db.session.add(doc)
        db.session.commit()
        return doc
    
    def parse_pdf(self, doc_record: DocumentProcessing) -> List[ExtractedItem]:
        """Parse PDF document and extract Q&A pairs"""
        items = []
        
        try:
            doc = fitz.open(doc_record.file_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                # Extract Q&A pairs
                qa_pairs = self.extract_qa_pairs(text)
                
                for i, (question, answer, confidence) in enumerate(qa_pairs):
                    # Get bounding boxes for question and answer
                    q_bbox = self.find_text_bbox(page, question)
                    a_bbox = self.find_text_bbox(page, answer) if answer else None
                    
                    # Create question item
                    q_item = ExtractedItem(
                        document_id=doc_record.id,
                        item_type='question',
                        content=question,
                        confidence_score=confidence,
                        page_number=page_num + 1,
                        bounding_box=q_bbox,
                        text_context=self.get_text_context(text, question)
                    )
                    items.append(q_item)
                    
                    # Create answer item if available
                    if answer:
                        a_item = ExtractedItem(
                            document_id=doc_record.id,
                            item_type='answer',
                            content=answer,
                            confidence_score=confidence,
                            page_number=page_num + 1,
                            bounding_box=a_bbox,
                            text_context=self.get_text_context(text, answer)
                        )
                        items.append(a_item)
                
                # Extract commitments
                commitments = self.extract_commitments(text)
                for commitment_text in commitments:
                    c_item = ExtractedItem(
                        document_id=doc_record.id,
                        item_type='commitment',
                        content=commitment_text,
                        confidence_score=0.8,
                        page_number=page_num + 1,
                        text_context=self.get_text_context(text, commitment_text)
                    )
                    items.append(c_item)
            
            doc.close()
            
        except Exception as e:
            current_app.logger.error(f"PDF parsing error: {str(e)}")
            raise
        
        return items
    
    def parse_excel(self, doc_record: DocumentProcessing) -> List[ExtractedItem]:
        """Parse Excel/CSV document and extract Q&A pairs"""
        items = []
        
        try:
            if doc_record.file_type == 'csv':
                df = pd.read_csv(doc_record.file_path)
            else:
                df = pd.read_excel(doc_record.file_path)
            
            # Look for Q&A patterns in columns
            for idx, row in df.iterrows():
                for col_idx, value in enumerate(row):
                    if pd.isna(value) or value == '':
                        continue
                    
                    text = str(value).strip()
                    if len(text) < 10:  # Skip very short texts
                        continue
                    
                    # Check if it's a question
                    if self.is_question(text):
                        item = ExtractedItem(
                            document_id=doc_record.id,
                            item_type='question',
                            content=text,
                            confidence_score=0.7,
                            text_context=f"Row {idx+1}, Column {col_idx+1}"
                        )
                        items.append(item)
                    
                    # Check for commitments
                    elif self.contains_commitment(text):
                        item = ExtractedItem(
                            document_id=doc_record.id,
                            item_type='commitment',
                            content=text,
                            confidence_score=0.8,
                            text_context=f"Row {idx+1}, Column {col_idx+1}"
                        )
                        items.append(item)
                    
                    # General content
                    else:
                        item = ExtractedItem(
                            document_id=doc_record.id,
                            item_type='statement',
                            content=text,
                            confidence_score=0.5,
                            text_context=f"Row {idx+1}, Column {col_idx+1}"
                        )
                        items.append(item)
        
        except Exception as e:
            current_app.logger.error(f"Excel/CSV parsing error: {str(e)}")
            raise
        
        return items
    
    def extract_qa_pairs(self, text: str) -> List[Tuple[str, str, float]]:
        """Extract Q&A pairs from text using pattern matching"""
        qa_pairs = []
        
        # Try each pattern
        for pattern in self.qa_patterns:
            matches = re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                content = match.group(1).strip()
                if len(content) < 10:  # Skip very short content
                    continue
                
                # Determine if it's a question or answer based on context
                is_question = any(word in content.lower() for word in ['?', 'what', 'how', 'when', 'where', 'why', 'which', 'who'])
                
                if is_question:
                    # Look for corresponding answer
                    answer_start = match.end()
                    answer_pattern = r'(?:^|\n)\s*(?:A\d*[\.\:]?\s*|Answer\s*\d*[\.\:]?\s*)(.+?)(?=\n|\Z)'
                    answer_match = re.search(answer_pattern, text[answer_start:], re.MULTILINE | re.IGNORECASE | re.DOTALL)
                    
                    answer = answer_match.group(1).strip() if answer_match else ""
                    confidence = 0.8 if answer else 0.6
                    
                    qa_pairs.append((content, answer, confidence))
        
        return qa_pairs
    
    def extract_commitments(self, text: str) -> List[str]:
        """Extract commitment statements from text"""
        commitments = []
        
        for pattern in self.commitment_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            for match in matches:
                # Get surrounding context
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end].strip()
                
                commitments.append(context)
        
        return commitments
    
    def is_question(self, text: str) -> bool:
        """Check if text is likely a question"""
        question_indicators = ['?', 'what', 'how', 'when', 'where', 'why', 'which', 'who', 'please', 'could', 'would']
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)
    
    def contains_commitment(self, text: str) -> bool:
        """Check if text contains commitment language"""
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.commitment_patterns)
    
    def find_text_bbox(self, page, text: str) -> Optional[Dict]:
        """Find bounding box for text in PDF page"""
        try:
            areas = page.search_for(text[:50])  # Search for first 50 chars
            if areas:
                rect = areas[0]  # Use first match
                return {
                    'x0': rect.x0, 'y0': rect.y0,
                    'x1': rect.x1, 'y1': rect.y1
                }
        except (IndexError, AttributeError):
            pass
        return None
    
    def get_text_context(self, full_text: str, target_text: str, context_size: int = 200) -> str:
        """Get surrounding text context"""
        try:
            start = full_text.find(target_text)
            if start == -1:
                return ""
            
            context_start = max(0, start - context_size)
            context_end = min(len(full_text), start + len(target_text) + context_size)
            
            return full_text[context_start:context_end].strip()
        except (AttributeError, IndexError):
            return ""
    
    def process_document(self, file_storage, uploaded_by: str) -> DocumentProcessing:
        """Main method to process uploaded document"""
        # Create document record
        doc_record = self.create_document_record(file_storage, uploaded_by)
        
        try:
            # Update status to processing
            doc_record.processing_status = 'processing'
            doc_record.processing_started = datetime.utcnow()
            db.session.commit()
            
            # Parse based on file type
            if doc_record.file_type == 'pdf':
                items = self.parse_pdf(doc_record)
            else:
                items = self.parse_excel(doc_record)
            
            # Save extracted items
            for item in items:
                db.session.add(item)
            
            # Update document record with results
            doc_record.processing_status = 'completed'
            doc_record.processing_completed = datetime.utcnow()
            doc_record.extracted_queries = len([i for i in items if i.item_type == 'question'])
            doc_record.extracted_qa_pairs = len([i for i in items if i.item_type in ['question', 'answer']]) // 2
            doc_record.extraction_confidence = sum(i.confidence_score or 0 for i in items) / len(items) if items else 0
            
            db.session.commit()
            
            current_app.logger.info(f"Successfully processed {doc_record.original_filename}: {len(items)} items extracted")
            
        except Exception as e:
            # Update status to failed
            doc_record.processing_status = 'failed'
            doc_record.processing_error = str(e)
            db.session.commit()
            
            current_app.logger.error(f"Failed to process {doc_record.original_filename}: {str(e)}")
            raise
        
        return doc_record
