import hashlib
import io
import re
from pathlib import Path

import PyPDF2
import pymupdf
import logging
from beanie import PydanticObjectId


from src.storages.mongo.models.document import Document_, DocumentCreate
from src.storages.mongo.models.task import TaskCreate
from src.storages.mongo.repositories.document import document_repository
from src.storages.mongo.repositories.task import task_repository
from src.storages.mongo.repositories.utils import utils_repository
from src.storages.mongo.models.utils import Utils, UtilsCreate, UtilsUpdate


class DocumentService:
    async def create(self, filename: str, file: bytes) -> Document_:
        checksum = hashlib.sha256(file).hexdigest()
        path = Path("files") / checksum

        document = await document_repository.read_by_path(path)
        if document is not None:
            return document

        with open(path, mode="wb") as file_:
            file_.write(file)

        task_ids = []
        parsed_tasks = self._parse_tasks_from_document(file)
        for parsed_task in parsed_tasks:
            task = await task_repository.create(parsed_task)
            await utils_repository.update_marks(task.marks)
            await utils_repository.update_years(task.year)
            task_ids.append(task.id)

        document = DocumentCreate(path=str(path), filename=filename, tasks=task_ids)
        return await document_repository.create(document)
    
    async def read(self, document_id: PydanticObjectId):
        document = await document_repository.read(document_id)
        if document is None:
            raise ValueError()
        
        return document
    
    async def read_all(self):
        return await document_repository.read_all()
    
    async def update(self, document_id: PydanticObjectId, document: Document_):
        return await document_repository.update(document_id=document_id, document_update=document)

    async def delete(self, document_id: PydanticObjectId):
        document = await document_repository.read(document_id)
        if document is None:
            raise ValueError()
        
        for task_id in document.tasks:
            await task_repository.delete(task_id)
        
        return await document_repository.delete(document_id)


    def __process_content(self, page):
        return page.replace('\n', '\\n').replace('\t', '\\t')

    def __process_questions(self, text):
        text = text.strip().replace('\\n', ' ').replace('\\t', ' ')
        text = self.clean_pattern.sub('', text)
        text = self.dot_fixer_pattern.sub('.', text)
        return ' '.join(text.split())

    def _parse_tasks_from_document(self, file: bytes) -> list[TaskCreate]:

        file_handler = logging.FileHandler('app.log')
        file_handler.setLevel(logging.DEBUG)  # Optionally set the level for the file handler
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)

        # Add the FileHandler to the root logger
        logging.getLogger('').addHandler(file_handler)

        try:
            date_pattern = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s\d{1,2}\s(January|February|March|April|May|June|July|August|September|October|November|December)\s(\d{4})"
            question_pattern = re.compile(r'(\([a-z]\)|\\n3)(.+?)\((\d{1,2})\)', re.DOTALL)

            self.clean_regex = r'\([a-z]\)|\\n3'
            self.clean_pattern = re.compile(self.clean_regex)

            self.dot_fixer_regex = r' \.'
            self.dot_fixer_pattern = re.compile(self.dot_fixer_regex)


            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file))

            
            first_page_text = pdf_reader.pages[0].extract_text()
            date = re.search(date_pattern, first_page_text)
            extracted_date = date.group(0) if date else None
            extracted_year = int(extracted_date[-4:]) if extracted_date else None

            

            
            extracted_questions = []
            
            pdffile = pymupdf.open(stream=file, filetype="pdf")
            for idx, page in enumerate(pdffile):
                page_content = page.get_text()
                matches = question_pattern.findall(self.__process_content(page_content))
                for match in matches:
                    extracted_questions.append({
                        'content': self.__process_questions(match[1]).lstrip('. '),
                        'marks': int(match[2]),
                        'year': extracted_year,
                        'page': idx + 1
                    })

            tasks = []
            with open("question.txt", "w") as o_file:
                print(extracted_questions, file=o_file)
            for question in extracted_questions:
                tasks.append(
                    TaskCreate(
                        content=question["content"],
                        marks=question["marks"],
                        year=question["year"],
                        page=question["page"],
                    )
                )

            return tasks
            
        except Exception as e:
    
            logging.error(f'An error occurred: {e}')
    



document_service = DocumentService()
