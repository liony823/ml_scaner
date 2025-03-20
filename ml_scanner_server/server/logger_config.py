import logging
from pathlib import Path

def setup_logging(log_dir=None):
    if log_dir:
        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)
        log_file = log_dir_path / 'server.log'
    else:
        log_file = 'server.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger()

def get_logger(name):
    return logging.getLogger(name) 