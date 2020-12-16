import pathlib
import attr

from pylexibank.providers.sndcmp import SNDCMP as BaseDataset
from pylexibank.providers.sndcmp import SNDCMPConcept


class Dataset(BaseDataset):
    dir = pathlib.Path(__file__).parent
    id = 'papuanvoices'

    study_name = 'WestPapua'
    source_id_array = []
    create_cognates = False

    form_placeholder = '►'
