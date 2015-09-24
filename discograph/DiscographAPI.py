# -*- encoding: utf-8 -*-
import os
import random
import re
try:
    from configparser import ConfigParser
except ImportError:
    from ConfigParser import ConfigParser
from abjad.tools import systemtools
from werkzeug.contrib.cache import FileSystemCache


class DiscographAPI(object):

    urlify_pattern = re.compile(r"\s+", re.MULTILINE)

    ### INITIALIZER ###

    def __init__(self, app=None):
        import discograph
        config_path = os.path.join(discograph.__path__[0], 'discograph.cfg')
        parser = ConfigParser()
        parser.read(config_path)
        if parser.has_option('cache', 'directory'):
            cache_path = parser.get('cache', 'directory')
        else:
            cache_path = os.path.join('..', 'tmp')
        cache_path = os.path.join(discograph.__path__[0], cache_path)
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)
        self._app = app
        self._cache = FileSystemCache(
            cache_path,
            default_timeout=60 * 60 * 24,
            )

    ### PUBLIC METHODS ###

    def cache_get(self, cache_key):
        data = self.cache.get(cache_key)
        if data is not None:
            print('Cache Hit:  {}'.format(cache_key))
            return data
        print('Cache Miss: {}'.format(cache_key))

    def cache_set(self, cache_key, data):
        self.cache.set(cache_key, data)

    def get_artist(self, artist_id):
        import discograph
        query = discograph.SQLArtist.select()
        query = query.where(discograph.SQLArtist.id == artist_id)
        result = list(query)
        if not result:
            return None
        return result[0]

    def get_artist_network(self, artist_id):
        import discograph
        cache_key = 'discograph:/api/artist/network/{}'.format(artist_id)
        data = self.cache_get(cache_key)
        if data is not None:
            return data
        artist = self.get_artist(artist_id)
        if artist is None:
            return None
        role_names = [
            'Alias',
            'Member Of',
            #'Producer',
            #'Guitar',
            #'Bass Guitar',
            #'Rhythm Guitar',
            #'Electric Guitar',
            #'Lead Guitar',
            #'Drums',
            #'Vocals',
            #'Lead Vocals',
            #'Backing Vocals',
            ]
        relation_grapher = discograph.RelationGrapher(
            center_entity=artist,
            degree=12,
            max_nodes=100,
            max_links=200,
            role_names=role_names,
            )
        with systemtools.Timer(exit_message='Network query time:'):
            data = relation_grapher.get_network_2()
        self.cache_set(cache_key, data)
        return data

    def get_random_entity(self):
        import discograph
        relation = discograph.SQLRelation.get_random()
        entity_choice = random.randint(1, 2)
        if entity_choice == 1:
            entity_type = relation.entity_one_type
            entity_id = relation.entity_one_id
        else:
            entity_type = relation.entity_two_type
            entity_id = relation.entity_two_id
        return entity_type, entity_id

    def search_entities(self, search_string):
        import discograph
        cache_key = 'discograph:/api/search/{}'.format(
            self.urlify_pattern.sub('+', search_string))
        data = self.cache_get(cache_key)
        if data is not None:
            return data
        query = discograph.SQLFTSArtist.search_bm25(search_string).limit(10)
        data = []
        for sql_fts_artist in query:
            datum = dict(
                key='artist-{}'.format(sql_fts_artist.id),
                name=sql_fts_artist.name,
                )
            data.append(datum)
            print('    {}'.format(datum))
        data = {'results': tuple(data)}
        self.cache_set(cache_key, data)
        return data

    ### PUBLIC PROPERTIES ###

    @property
    def app(self):
        return self._app

    @property
    def cache(self):
        return self._cache