from __future__ import print_function
import gzip
import mongoengine
import traceback
from abjad.tools import systemtools
from discograph.bootstrap import Bootstrap
from discograph.models.ArtistReference import ArtistReference
from discograph.models.Model import Model


class Artist(Model, mongoengine.Document):

    ### MONGOENGINE FIELDS ###

    discogs_id = mongoengine.IntField(primary_key=True)
    name = mongoengine.StringField(required=True, unique=True)
    real_name = mongoengine.StringField()
    name_variations = mongoengine.ListField(mongoengine.StringField())
    aliases = mongoengine.EmbeddedDocumentListField('ArtistReference')
    members = mongoengine.EmbeddedDocumentListField('ArtistReference')
    groups = mongoengine.EmbeddedDocumentListField('ArtistReference')
    #has_been_scraped = mongoengine.BooleanField(default=False)

    ### MONGOENGINE META ###

    meta = {
        'indexes': [
            '#name',
            '$name',
            'discogs_id',
            'name',
            ],
        }

    ### PRIVATE PROPERTIES ###

    @property
    def _storage_format_specification(self):
        keyword_argument_names = sorted(self._fields)
        if 'id' in keyword_argument_names:
            keyword_argument_names.remove('id')
        for keyword_argument_name in keyword_argument_names[:]:
            value = getattr(self, keyword_argument_name)
            if isinstance(value, list) and not value:
                keyword_argument_names.remove(keyword_argument_name)
        return systemtools.StorageFormatSpecification(
            self,
            keyword_argument_names=keyword_argument_names,
            )

    ### PUBLIC METHODS ###

    @classmethod
    def bootstrap(cls):
        cls.drop_collection()
        # Pass one.
        artists_xml_path = Bootstrap.artists_xml_path
        with gzip.GzipFile(artists_xml_path, 'r') as file_pointer:
            iterator = Bootstrap.iterparse(file_pointer, 'artist')
            iterator = Bootstrap.clean_elements(iterator)
            for i, element in enumerate(iterator):
                try:
                    with systemtools.Timer(verbose=False) as timer:
                        document = cls.from_element(element)
                        document.save()
                    message = u'{} (Pass 1) {} [{}]: {}'.format(
                        cls.__name__.upper(),
                        document.discogs_id,
                        timer.elapsed_time,
                        document.name,
                        )
                    print(message)
                except mongoengine.errors.ValidationError:
                    traceback.print_exc()

        # Pass two.
        count = cls.objects.count()
        for index in range(count):
            document = cls.objects.no_cache()[index]
            with systemtools.Timer(verbose=False) as timer:
                changed = document.resolve_references()
                if changed:
                    document.save()
                    message = u'{} (Pass 2) {} [{}]: {}'.format(
                        cls.__name__.upper(),
                        document.discogs_id,
                        timer.elapsed_time,
                        document.name,
                        )
                    print(message)

    @classmethod
    def from_element(cls, element):
        data = cls.tags_to_fields(element)
        document = cls(**data)
        return document

    def get_relations(
        self,
        include_aliases=False,
        exclude_trivial=False,
        ):
        from discograph import models
        ids = [self.discogs_id]
        if include_aliases:
            for alias in self.aliases:
                query = models.Artist.objects(name=alias)
                query = query.hint([('name', 'hashed')])
                if not query.count():
                    continue
                alias = query.first()
                ids.append(alias.discogs_id)
        composite = (
            mongoengine.Q(
                entity_one_id__in=ids,
                entity_one_type=models.Relation.EntityType.ARTIST,
                ) |
            mongoengine.Q(
                entity_two_id__in=ids,
                entity_two_type=models.Relation.EntityType.ARTIST,
                )
            )
        query = models.Relation.objects(composite)
        if exclude_trivial:
            query = query(is_trivial__ne=True)
        return query

    def get_relation_counts(
        self,
        include_aliases=False,
        exclude_trivial=False,
        ):
        query = self.get_relations(
            include_aliases=include_aliases,
            exclude_trivial=exclude_trivial,
            )
        query = query.item_frequencies('year')
        results = sorted(
            (year, count)
            for year, count in query.items()
            if year
            )
        return results

    def get_relation_agggregate(
        self,
        include_aliases=False,
        exclude_trivial=False,
        ):
        from discograph import models
        ids = [self.discogs_id]
        if include_aliases:
            for alias in self.aliases:
                query = models.Artist.objects(name=alias)
                query = query.hint([('name', 'hashed')])
                if not query.count():
                    continue
                alias = query.first()
                ids.append(alias.discogs_id)
        query = models.Relation.objects.aggregate(
            {'$match': {
                'entity_one_id': {'$in': ids},
                'entity_one_type': 1,
                'year': {'$exists': 1},
                }},
            {'$group': {
                '_id': {
                    'year': '$year',
                    'role_name': '$role_name',
                    },
                'total': {'$sum': 1}
                }},
            {'$group': {
                '_id': '$_id.year',
                'totals': {
                    '$push': {
                        'role_name': '$_id.role_name',
                        'total': '$total',
                        },
                    },
                }},
            {'$project': {'_id': 0, 'year': '$_id', 'totals': '$totals'}},
            {'$sort': {'year': 1}}
            )
        return query

    def resolve_references(self):
        changed = False
        for artist_reference in self.aliases:
            query = type(self).objects(name=artist_reference.name)
            query = query.only('discogs_id', 'name')
            found = list(query)
            if not len(found):
                continue
            artist_reference.discogs_id = found[0].discogs_id
            changed = True
        for artist_reference in self.groups:
            query = type(self).objects(name=artist_reference.name)
            query = query.only('discogs_id', 'name')
            found = list(query)
            if not len(found):
                continue
            artist_reference.discogs_id = found[0].discogs_id
            changed = True
        return changed


Artist._tags_to_fields_mapping = {
    'id': ('discogs_id', Bootstrap.element_to_integer),
    'name': ('name', Bootstrap.element_to_string),
    'realname': ('real_name', Bootstrap.element_to_string),
    'namevariations': ('name_variations', Bootstrap.element_to_strings),
    'aliases': ('aliases', ArtistReference.from_names),
    'groups': ('groups', ArtistReference.from_names),
    'members': ('members', ArtistReference.from_members),
    }