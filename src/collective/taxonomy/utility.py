# -*- coding: utf-8 -*-

import generated

from BTrees.OOBTree import OOBTree

from zope import schema
from zope.component import getMultiAdapter
from zope.component.hooks import getSite
from zope.interface import implements
from zope.interface.interface import InterfaceClass, Interface
from zope.i18nmessageid import MessageFactory
from zope.schema.interfaces import IVocabulary
from zope.schema.vocabulary import SimpleTerm

from plone.behavior.interfaces import IBehavior
from plone.behavior.registration import BehaviorRegistration
from plone.supermodel.model import SchemaClass

from persistent.dict import PersistentDict
from persistent import Persistent

from .interfaces import ITaxonomy


class Taxonomy(PersistentDict):
    implements(ITaxonomy)

    @property
    def current_language(self):
        context = getSite()
        portal_state = getMultiAdapter(
            (context, context.REQUEST),
            name=u'plone_portal_state')
        current_language = portal_state.language()
        return current_language

    def registerBehaviour(self):
        schema = SchemaClass("Schema", (Interface,),
                             __module__="collective.taxonomy.generated",
                             attrs = {})

        registration = BehaviorRegistration(title='Sample dynamic behavior',
                                        description='',
                                        interface=schema,
                                        marker=None,
                                        factory=None)

        import pdb; pdb.set_trace()

    def __init__(self, name, title):
        super(Taxonomy, self).__init__(self)
        self.name = name
        self.title = title
        self.registerBehaviour()

    def add(self, language, identifier, path):
        if not language in self:
            self[language] = OOBTree()

        self[language][path] = identifier

    def translate(self, msgid, mapping=None, context=None,
                  target_language=None, default=None):
        # XXX: This is slow
        if target_language is None:
            target_language = self.current_language
        if target_language not in self:
            raise Exception("Target language is not defined")

        result = [(identifier, path) for
                  (identifier, path) in self[target_language].byValue(msgid) if
                  identifier == msgid]

        if len(result) < 0:
            raise Exception("Translation not found")

        ((identifier, path), ) = result
        return path

    def __call__(self, context):
        current_language = self.current_language
        data = self[current_language]
        return Vocabulary(self.name, data)


class Vocabulary(object):
    implements(IVocabulary)

    def __init__(self, name, data):
        self.data = data
        self.message = MessageFactory(name)

    def getTerms(self):
        results = []

        for (path, identifier) in \
                self.data.items():

            results.append(SimpleTerm(value=path,
                                      title=self.message(identifier, path)))

        return results
