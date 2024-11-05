import csv
import logging
import os

MAP_CUSTOM = {}
CLEANING_DIR = 'utils/cleaning'

def load_cmap_custom(format_file_name):
    """
    Load the custom map from the given file name.
    """
    if format_file_name in MAP_CUSTOM:
        return MAP_CUSTOM[format_file_name]
    
    cmap_dict = {}
    file_path = os.path.join(CLEANING_DIR, format_file_name)
    with open(file_path, mode='r') as infile:
        logging.info(f'Loading file: {format_file_name}')
        reader = csv.reader(infile)
        for row in reader:
            if len(row) == 2:
                cmap_dict[row[0]] = row[1]
            else:
                logging.warning(f'Invalid row format in {format_file_name}: {row}')
    
    MAP_CUSTOM[format_file_name] = cmap_dict
    return cmap_dict

def replace_text_in_files(text, replacement_file_name=None):
    """
    Replace the text with the custom map.
    """
    # GET the format file list
    format_files = [replacement_file_name] if replacement_file_name else MAP_CUSTOM.keys()
    for format_file_name in format_files:
        # Load the custom map
        replacements = load_cmap_custom(format_file_name)
        # Replace the old string with the new string
        for old, new in replacements.items():
            text = text.replace(old, new)
    return text

# Preload default map
load_cmap_custom("cmap_custom.csv")
