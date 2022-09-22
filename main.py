import subprocess, logging, shutil
from uuid import uuid4
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from tempfile import NamedTemporaryFile
from utils import *
import tempfile
from typing import Union

api = FastAPI(
  title="ATRAC API"
)
logger = logging.getLogger("uvicorn.info")
@api.on_event("startup")
async def startup_event():
  api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )

@api.get("/")
async def root():
    return RedirectResponse("/docs")

@api.post('/encode')
def encode_atrac(type: atracTypes, background_tasks: BackgroundTasks, file: UploadFile = File()):
  global logger
  if type not in ['LP2', 'LP4']:
    raise HTTPException(status_code=400, detail="Invalid encoding type")
  filename = file.filename
  logger.info(f"Beginning encode for {filename}")
  output = NamedTemporaryFile(delete=False)
  with NamedTemporaryFile() as input:
    shutil.copyfileobj(file.file, input)
    encoder = subprocess.run(['/usr/bin/wine', 'psp_at3tool.exe', '-e', '-br', str(bitrates[type]), 
      Path(input.name), 
      Path(output.name)], capture_output=True)
    logger.info(encoder.stdout.decode())
    background_tasks.add_task(remove_file, output.name, logger)
    return FileResponse(path=output.name, filename=Path(filename).stem + '.at3')

@api.post('/transcode')
def transcode_atrac(type: atracTypes, background_tasks: BackgroundTasks, applyReplaygain: bool = False, loudnessTarget: Union[float, None] = None, file: UploadFile = File()):
  global logger
  if type not in ['LP2', 'LP4']:
    raise HTTPException(status_code=400, detail="Invalid encoding type")
  filename = file.filename
  logger.info(f"Beginning encode for {filename}")

  transcoderCommands = []
  if loudnessTarget is not None:
    if loudnessTarget not in range(-70, -5):
      raise HTTPException(status_code=400, detail="Can only normalize loudness from -70 to -5 dB")
    transcoderCommands.append(f'-filter_complex')
    transcoderCommands.append(f'-loudnorm=I={loudnessTarget}')
  elif applyReplaygain:
    transcoderCommands.append('-af')
    transcoderCommands.append('volume=replaygain=track')
  
  transcoderCommands += ['-ac', '2', '-ar', '44100', '-f', 'wav']

  with NamedTemporaryFile() as input:
    intermediary = Path(tempfile.gettempdir(), str(uuid4())).absolute()
    output = Path(tempfile.gettempdir(), str(uuid4())).absolute()

    shutil.copyfileobj(file.file, input)
    logger.info("Starting ffmpeg...")
    transcoder = subprocess.run([
      '/usr/bin/ffmpeg', '-i',
      Path(input.name),
      *transcoderCommands,
      intermediary], capture_output=True)
    logger.info(transcoder.stdout.decode())
    logger.info("Starting at3tool...")
    encoder = subprocess.run(['/usr/bin/wine', 'psp_at3tool.exe', '-e', '-br', str(bitrates[type]), 
      Path(intermediary), 
      output], capture_output=True)
    logger.info(encoder.stdout.decode())
    
    background_tasks.add_task(remove_file, output, logger)
    background_tasks.add_task(remove_file, intermediary, logger)
    
    return FileResponse(path=output, filename=Path(filename).stem + '.at3')

@api.post('/decode')
def decode_atrac(background_tasks: BackgroundTasks, file: UploadFile = File()):
  global logger
  filename = file.filename
  logger.info(f"Beginning decode for {filename}")
  output = NamedTemporaryFile(delete=False)
  with NamedTemporaryFile() as input:
    shutil.copyfileobj(file.file, input)
    encoder = subprocess.run(['/usr/bin/wine', 'psp_at3tool.exe', '-d', 
      Path(input.name), 
      Path(output.name)], capture_output=True)
    logger.info(encoder.stdout.decode())
    background_tasks.add_task(remove_file, output.name, logger)
    return FileResponse(path=output.name, filename=Path(filename).stem + '.wav')