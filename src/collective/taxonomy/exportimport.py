from elementtree import ElementTree

from zope.interface import Interface, implements, implementedBy
from zope.component import queryUtility
from zope import schema

from zope.schema.interfaces import IField
from zope.schema.interfaces import IVocabularyTokenized
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from plone.supermodel.utils import indent, elementToValue, valueToElement, ns

from .interfaces import ITaxonomy
from .utility import Taxonomy

from collections import OrderedDict

def importTaxonomy(context):
    logger = context.getLogger('collective.taxonomy')
    body = context.readDataFile('taxonomies.xml')
    if body is not None:
        importer = TaxonomyImportExportAdapter(context)
        importer.importDocument(body)


def exportTaxonomy(context):
    logger = context.getLogger('collective.taxonomy')
    exporter = TaxonomyImportExportAdapter(context)
    body = exporter.exportDocument()
    if body is not None:
        context.writeDataFile('taxonomies.xml', body, 'text/xml')

class importVdex(object):
    def __init__(self, tree, ns):
        self.tree = tree
        self.ns = ns

    def __call__(self):
        languages = set()
        results = self.recurse(self.tree, languages)
        final_results = {}
        for language in languages:
            final_results[language] = self.process_language(results, language)

        return final_results

    def process_language(self, results, language, path=('',)):
        result = {}
        for element in results.keys():
            (lang, identifier, children, parent_identifier) = results[element]
            if lang == language:
                result['/'.join(path) + '/' + element] = (identifier, parent_identifier)
                result.update(self.process_language(children, language, path + (element,)))
        return result

    def recurse(self, tree, available_languages=set(), parent_language=None, parent_identifier=-1):
        result = {}

        for node in tree.findall('./{%s}term' % self.ns):
            identifier = node.find('./{%s}termIdentifier' % self.ns)
            langstrings = node.findall('./{%s}caption/{%s}langstring' % (self.ns, self.ns))
            for i in langstrings:
                if not parent_language or parent_language == i.attrib['language']:
                    result[i.text] = (i.attrib['language'],
                                      int(identifier.text),
                                      self.recurse(node, available_languages, i.attrib['language'], int(identifier.text)),
                                      parent_identifier)

                available_languages.add(i.attrib['language'])

        return result

class exportVdex(object):
    def __init__(self, taxonomy):
        self.taxonomy = taxonomy

    def buildFinalPathIndex(self, node, tree):
        results = {}

        for i in node:
            # leaf
            if not tree.has_key(i):
                results[i] = {}
            else:
                results[i] = self.buildFinalPathIndex(tree[i], tree)

        return results

    def buildPathIndex(self):
        pathIndex = {}
        finalPathIndex = {}

        for (language, children) in self.taxonomy.items():
            for (path, (identifier, parent_identifier)) in children.items():
                if not pathIndex.has_key(parent_identifier):
                    pathIndex[parent_identifier] = set()
                pathIndex[parent_identifier].add(identifier)

        if not pathIndex.has_key(-1):
            raise Exception("No root node!")

        return self.buildFinalPathIndex(pathIndex[-1], pathIndex)

    def makeTranslationTable(self):
        translationTable = {}

        for (language, children) in self.taxonomy.items():
            for (path, (identifier, parent_identifier)) in children.items():
                if not translationTable.has_key(identifier):
                    translationTable[identifier] = {}

                translationTable[identifier][language] = path[path.rfind('/')+1:]

        return translationTable

    def makeSubtree(self, index, table):
        termnodes = []
        for identifier in index.keys():
            termnode = ElementTree.Element('term')
            identifiernode = ElementTree.Element('termIdentifier')
            identifiernode.text = str(identifier)
            captionnode = ElementTree.Element('caption')

            translations = table[identifier].items()
            translations.sort(key=lambda (language, langstring) : language)

            for (language, langstring) in translations:
                langstringnode = ElementTree.Element('langstring')
                langstringnode.text = langstring
                langstringnode.attrib['language'] = language
                captionnode.append(langstringnode)

            termnode.append(identifiernode)
            termnode.append(captionnode)

            for nestedtermnode in self.makeSubtree(index[identifier], table):
                termnode.append(nestedtermnode)

            # add to list
            termnodes.append(termnode)

        return termnodes

class TaxonomyImportExportAdapter(object):
    """Helper classt to import a registry file
    """

    LOGGER_ID = 'collective.taxonomy'
    IMSVDEX_NS = 'http://www.imsglobal.org/xsd/imsvdex_v1p0'
    IMSVDEX_ATTRIBS = {'xmlns':"http://www.imsglobal.org/xsd/imsvdex_v1p0",
                       'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
                       'xsi:schemaLocation' : "http://www.imsglobal.org/xsd/imsvdex_v1p0 "
                       "imsvdex_v1p0.xsd http://www.imsglobal.org/xsd/imsmd_rootv1p2p1 "
                       "imsmd_rootv1p2p1.xsd",
                       'orderSignificant' : "false",
                       'profileType' : "hierarchicalTokenTerms",
                       'language' : "en"
                       }
    IMSVDEX_ENCODING = 'utf-8'

    def __init__(self, context, environ):
        self.context = context
        self.logger = environ.getLogger(self.LOGGER_ID)

    def importDocument(self, document):
        tree = ElementTree.fromstring(document)
        title = tree.find('./{%s}vocabName/{%s}langstring' % (self.IMSVDEX_NS, self.IMSVDEX_NS))
        name = tree.find('./{%s}vocabIdentifier' % self.IMSVDEX_NS)

        utility_name = 'collective.taxonomy.' + name.text
        taxonomy = queryUtility(ITaxonomy, name=name.text)

        if not taxonomy:
            taxonomy = Taxonomy(title.text)
            sm = self.context.getSiteManager()
            sm.registerUtility(taxonomy, ITaxonomy, name=utility_name)

        if taxonomy and self.environ.shouldPurge():
            taxonomy.clear()

        results = importVdex(tree, self.IMSVDEX_NS)()

        for (language, elements) in results.items():
            for (path, (identifier, parent_identifier)) in elements.items():
                taxonomy.add(language, int(identifier), path, parent_identifier)

        return utility_name

    def exportDocument(self, name):
        taxonomy = queryUtility(ITaxonomy, name=name)

        root = ElementTree.Element('vdex', attrib=self.IMSVDEX_ATTRIBS)

        vocabName = ElementTree.Element('vocabName')
        root.append(vocabName)

        langstring = ElementTree.Element('langstring', attrib={'language' : 'en'})
        langstring.text = taxonomy.title

        vocabName.append(langstring)

        vocabIdentifier = ElementTree.Element('vocabIdentifier')
        vocabIdentifier.text = name.replace('collective.taxonomy.', '')

        root.append(vocabIdentifier)

        helper = exportVdex(taxonomy)
        index = helper.buildPathIndex()
        table = helper.makeTranslationTable()
        for termnode in helper.makeSubtree(index, table):
            root.append(termnode)

        indent(root)
        treestring = ElementTree.tostring(root, self.IMSVDEX_ENCODING)
        header = """<?xml version="1.0" encoding="%s"?>""" % self.IMSVDEX_ENCODING.upper() + '\n'
        treestring = header + treestring
        return treestring


