import pathlib
import attr
import itertools
import csv

from pylexibank import Dataset as BaseDataset
from pylexibank import Language, Concept, FormSpec
from pylexibank import progressbar
from csvw.metadata import URITemplate
import collections


ROLE_MAP = {
    'ContributorPhoneticTranscriptionBy': 'phonetic_transcriptions',
    'ContrbutorPhoneticTranscriptionBy': 'phonetic_transcriptions',
    'ContrbutorRecordedBy': 'recording',
    'ContributorRecordedBy1': 'recording',
    'ContributorSoundEditingBy': 'sound_editing',
    'ContrbutorSoundEditingBy': 'sound_editing',
    'ContributorRecordedBy2': 'recording',
    'ContributorReconstructionBy': 'reconstruction',
}


@attr.s
class CustomLanguage(Language):
    LongName = attr.ib(default=None)
    IsProto = attr.ib(default=None)


@attr.s
class CustomConcept(Concept):
    Papuan_Malay_Gloss = attr.ib(default=None)


class Dataset(BaseDataset):
    dir = pathlib.Path(__file__).parent
    id = 'papuanvoices'

    form_spec = FormSpec(
            replacements=[],
            missing_data=['..'],
            normalize_unicode='NFC',
            strip_inside_brackets=False,
            )

    concept_class = CustomConcept
    language_class = CustomLanguage

    def cmd_makecldf(self, args):

        sc_fp_map = {}  # old cat format lg file path map
        with open(self.etc_dir / 'sc_fp_map.tsv', 'r') as f:
            for x in f:
                m = x.strip().split('\t')
                if m[1] != 'NULL':  # only non-proto lgs
                    sc_fp_map[m[0]] = m[1]

        sc_wp_map = {}  # old cat format word file path map
        sc_p_map = {}  # old cat format parameter map

        with args.writer as ds:
            ds.add_sources()

            for concept in self.concepts:
                sc_p_map[concept['ID']] = concept['IndexInSource']
                del concept['IndexInSource']
                ds.add_concept(**concept)

            with open(self.etc_dir / 'sc_wp_map.tsv', 'r') as f:
                for x in f:
                    m = x.strip().split('\t')
                    sc_wp_map[m[0]] = m[1]

            known_param_ids = set([d['ID'] for d in ds.objects['ParameterTable']])

            ds.cldf.add_component(
                'MediaTable',
                'objid',
                {'name': 'size', 'datatype': 'integer'},
                {
                    'name': 'Form_ID',
                    'required': True,
                    'propertyUrl': 'http://cldf.clld.org/v1.0/terms.rdf#formReference',
                    'datatype': 'string'
                },
                {
                    'name': 'mimetype',
                    'required': True,
                    'datatype': {'base': 'string', 'format': '[^/]+/.+'}
                },
            )
            ds.cldf.remove_columns('MediaTable', 'Download_URL')
            ds.cldf.remove_columns('MediaTable', 'Description')
            ds.cldf.remove_columns('MediaTable', 'Path_In_Zip')
            ds.cldf.remove_columns('MediaTable', 'Media_Type')
            ds.cldf['MediaTable', 'ID'].valueUrl = URITemplate('https://cdstar.eva.mpg.de/bitstreams/{objid}/{Name}')
            ds.cldf['MediaTable', 'mimetype'].propertyUrl = URITemplate('http://cldf.clld.org/v1.0/terms.rdf#mediaType')

            sound_cat = self.raw_dir.read_json('catalog_pv.json')
            sound_map = dict()
            for k, v in sound_cat.items():
                sound_map[v['metadata']['name']] = k

            # load old cat format
            sound_cat_old = self.raw_dir.read_json('catalog.json')
            for k, v in sound_cat_old.items():
                sound_map[v['metadata']['name']] = v['id']
                sound_cat[v['id']] = v

            for lang_dir in progressbar(
                    sorted((self.raw_dir / 'data').iterdir(), key=lambda f: f.name),
                    desc="adding new data"):

                if lang_dir.name.startswith('.') or not (lang_dir / 'languages.csv').exists():
                    continue

                lang_id = lang_dir.name

                with open(lang_dir / 'languages.csv') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        language = row
                        break
                source = language['Source']
                del language['Source']
                del language['ORG_LG_NAME']
                if 'IndexInSource' in language:
                    del language['IndexInSource']
                ds.add_language(**language)

                seen_lexemes_old = collections.defaultdict(lambda: 1)
                seen_lexemes_new = collections.defaultdict(lambda: 1)
                seen_pron2 = collections.defaultdict(lambda: False)

                # Do not sort data.csv files - form id index refers to import
                with open(lang_dir / 'data.csv') as f:
                    reader = csv.reader(f)
                    for i, row in enumerate(reader):
                        value = row[0].strip()
                        if i > 0:
                            param_id = row[1].strip()
                            comment = row[2].strip() if len(row) > 2 else None
                            if param_id in known_param_ids:
                                if value == '►' or language['IsProto'] == 'True':
                                    new = ds.add_form_with_segments(
                                        Language_ID=lang_id,
                                        Local_ID='',
                                        Parameter_ID=param_id,
                                        Value=value,
                                        Form=self.form_spec.clean(self.lexemes.get(value, value)),
                                        Segments=[''],
                                        Comment=comment,
                                        Loan=False,
                                        Source=source,
                                    )
                                else:
                                    new = ds.add_form(
                                        Language_ID=lang_id,
                                        Local_ID='',
                                        Parameter_ID=param_id,
                                        Value=value,
                                        Form=self.form_spec.clean(self.lexemes.get(value, value)),
                                        Comment=comment,
                                        Loan=False,
                                        Source=source,
                                    )

                                # try old media IDs first
                                old_id = False
                                media_id = None

                                if lang_id in sc_fp_map and param_id in sc_p_map and sc_p_map[param_id] in sc_wp_map:
                                    lex_idx = seen_lexemes_old[param_id]
                                    if lex_idx == 1:
                                        media_id = '{}{}'.format(sc_fp_map[lang_id],
                                                                 sc_wp_map[sc_p_map[param_id]])
                                    else:
                                        media_id = '{}{}_lex{}'.format(sc_fp_map[lang_id],
                                                                       sc_wp_map[sc_p_map[param_id]],
                                                                       lex_idx)
                                    old_id = True

                                # if no old media ID is found try it with _pron2 (there're only _pron2 without _lex)
                                if media_id is None or (media_id not in sound_map or sound_map[media_id] not in sound_cat):
                                    old_id = False
                                    media_id = None
                                    if lang_id in sc_fp_map and param_id in sc_p_map and sc_p_map[param_id] in sc_wp_map:
                                        lex_idx = seen_lexemes_old[param_id]
                                        media_id = '{}{}_pron2'.format(sc_fp_map[lang_id], sc_wp_map[sc_p_map[param_id]])
                                        if seen_pron2[media_id]:
                                            media_id = None
                                        else:
                                            old_id = True

                                # if no old media ID is found take new ones
                                if media_id is None or (media_id not in sound_map or sound_map[media_id] not in sound_cat):
                                    lex_idx = seen_lexemes_new[param_id]
                                    if lex_idx == 1:
                                        media_id = '{}_{}'.format(lang_id, param_id)
                                    else:
                                        media_id = '{}_{}__{}'.format(lang_id, param_id, lex_idx)
                                    old_id = False

                                if media_id is not None and media_id in sound_map and sound_map[media_id] in sound_cat:
                                    if old_id:
                                        seen_lexemes_old[param_id] += 1
                                        if media_id.endswith('_pron2'):
                                            seen_pron2[media_id] = True
                                    else:
                                        seen_lexemes_new[param_id] += 1

                                    for bs in sorted(sound_cat[sound_map[media_id]]['bitstreams'],
                                                     key=lambda x: x['content-type']):
                                        ds.objects['MediaTable'].append({
                                            'ID': bs['checksum'],
                                            'Name': bs['bitstreamid'],
                                            'objid': sound_map[media_id],
                                            'mimetype': bs['content-type'],
                                            'size': bs['filesize'],
                                            'Form_ID': new['ID'],
                                        })

            ds.cldf.add_component(
                'ContributionTable',
                'phonetic_transcriptions',
                'recording',
                'sound_editing',
                'reconstruction',
                {
                    "name": "Language_ID",
                    "required": True,
                    "propertyUrl": "http://cldf.clld.org/v1.0/terms.rdf#languageReference",
                    "datatype": "string"
                },
            )
            ds.cldf.remove_columns('ContributionTable', 'Name')
            ds.cldf.remove_columns('ContributionTable', 'Description')
            ds.cldf.remove_columns('ContributionTable', 'Contributor')
            ds.cldf.remove_columns('ContributionTable', 'Citation')

            args.writer.cldf['FormTable', 'Value'].common_props['dc:description'] = \
                '► := no value, but audio'
            args.writer.cldf['FormTable', 'Form'].common_props['dc:description'] = \
                '► := no form, but audio'

            for lid, contribs in itertools.groupby(
                sorted(
                    self.raw_dir.read_csv('contributions.csv', dicts=True),
                    key=lambda r: (r['Language_ID'], r['Role'])),
                lambda r: r['Language_ID']
            ):
                res = dict(
                    ID=lid,
                    phonetic_transcriptions='',
                    recording='',
                    sound_editing='',
                    reconstruction='',
                    Language_ID=lid,
                )
                for contrib in contribs:
                    k = ROLE_MAP[contrib['Role']]
                    if res[k]:
                        res[k] += ' and '
                    res[k] += contrib['Contributor']
                args.writer.objects['contributions.csv'].append(res)

            ds.objects['FormTable'].sort(key=lambda r: (r['Language_ID'], int(r['Parameter_ID'].split('_')[0]), r['ID']))
