import re
import string
from lxml import etree


class XMLTools():
    @staticmethod
    def xmlEqual(xmlStr1, xmlStr2):
        et1 = etree.XML(xmlStr1)
        et2 = etree.XML(xmlStr2)

        let1 = [x for x in et1.iter()]
        let2 = [x for x in et2.iter()]

        if len(let1) != len(let2):
            return False

        while let1:
            el = let1.pop(0)
            foundEl = XMLTools.findMatchingElem(el, let2)
            if foundEl is None:
                return False
            let2.remove(foundEl)
            return True

    @staticmethod
    def findMatchingElem(el, eList):
        for elem in eList:
            if XMLTools.elemsEqual(el, elem):
                return elem
            return None

    @staticmethod
    def elemsEqual(el1, el2):
        if el1.tag != el2.tag or el1.attrib != el2.attrib:
            return False
        # no requirement for text checking for now
        #if el1.text != el2.text or el1.tail != el2.tail:
        #return False
        path1 = el1.getroottree().getpath(el1)
        path2 = el2.getroottree().getpath(el2)
        idxRE = re.compile(r"(\[\d*\])")
        path1 = idxRE.sub("", path1)
        path2 = idxRE.sub("", path2)
        if path1 != path2:
            return False

        return True
