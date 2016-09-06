"""HTML templating with no shame

>>> from lys import L
>>> str(L.h1 / 'hello world')
'<h1>hello world</h1>'
>>> str(L.hr('.thick')))
'<hr class='thick'/>'
>>> str(L.button(onclick='reverse_entropy()'))
'<button onclick='reverse_entropy()'/>'
>>> str(L.ul / (
    L.li / 'One',
    L.li / 'Two',
))
'<ul><li>One</li><li>Two</li></ul>'
"""

import re
import sys
import html
import types
import logging

logger = logging.getLogger(__name__)

if sys.version_info >= (3,):
    unicode = str


__all__ = [
    'L',
    'LysExcept',
    'raw'
]


VOID_TAGS = [
    'area', 'base', 'br', 'col', 'embed', 'hr',
    'img', 'input', 'keygen', 'link', 'meta',
    'param', 'source', 'track', 'wbr'
]

rgx_class  = re.compile(r'([\.\#]-?[_a-z]+[_a-z0-9\-]*)', re.I)
rgx_n_attr = re.compile(r'\[([_a-z0-9\-]+)\=["\']?([\w\s]+)["\']?\]', re.I)


class LyxException(Exception):
    """ Base exception class for all Lys related errors. """


class InvalidAttribute(ValueError, LyxException):
    """ Raised when key for a tag attribute is invalid. """


class MismatchedGrouping(ValueError, LyxException):
    """ Raised during shortcut processing when character groups
        have a different number of starting and ending values. """


def render_attr(key, value, attr_format='{key}="{value}"'):
    """ Formats key-value pairs into a string.

        Args:
            key (str)
            value: a value that can be cast as a string for
                formatting.
            attr_format (str): the template used to render
                the key-value pairs to be returned as strings
                used in the tags.

        Returns:
            str

        Raises:
            InvalidAttribute: when ``key`` is unset, or contains
                an invalid ``<space>`` character.
    """

    if not key or ' ' in key:
        raise InvalidAttribute('Invalid name "{}"'.format(key))

    if value:
        if type(value) is RawNode:
            value = str(value)
        else:
            value = html.escape(str(value))

        return attr_format.format(key=key, value=value)

    return key


def render(node, sort_attrs=True):
    """

        Args:
            node (:obj:`.Node`)
            sort_attrs (bool): should the tag attributes be
                sorted before rendering them into the tag.

        Returns:
            str
    """
    if node is None:
        return ''

    if type(node) is RawNode:
        return node.content

    if type(node) in (tuple, list, types.GeneratorType):
        return ''.join(render(child) for child in node)

    if type(node) in (str, unicode):
        return html.escape(node)

    children_rendered = render(node.children) if node.children else ''
    attrs_rendered = ''

    if node.attrs:
        attrs = sorted(node.attrs) if sort_attrs else node.attrs
        attrs_rendered = ' '.join(render_attr(k, node.attrs[k]) for k in attrs)

    sp = ' ' if attrs_rendered else ''

    if node.tag in VOID_TAGS:
        ret = '<{tag}{sp}{attrs}/>'.format(
            tag=node.tag, sp=sp, attrs=attrs_rendered)

    else:
        ret = '<{tag}{sp}{attrs}>{children}</{tag}>'.format(
            tag=node.tag, sp=sp, attrs=attrs_rendered, children=children_rendered)

    return ret


def process_shortcut(s):
    """ Converts the CSS shortcut string into a valid inner-tag.

        Args:
            s (str): value to be processed

        Returns:
            dict

        Raises:
            :obj:`.MismatchedGrouping`
    """
    if s.count('[') != s.count(']'):
        raise MismatchedGrouping('Invalid grouping of brackets, %s' % s)

    if s.count('"') % 2 != 0 or s.count("'") % 2 != 0:
        raise MismatchedGrouping('Quotation groupings are mismatched, %s' % s)

    ret_dict = {}

    # find the classes and id
    for match in rgx_class.findall(s):
        if match.startswith('#'):
            ret_dict.setdefault('id', match.strip('#'))

        elif match.startswith('.'):
            classes = ret_dict.setdefault('_classes', [])
            classes.append(match.strip('.'))

    # find all of our named attributes
    for key, value in rgx_n_attr.findall(s):
        ret_dict.setdefault(key, value)

    ret_dict['class'] = ret_dict.pop('_classes', [])

    return ret_dict


class Node(object):
    """ An object whose instance represents an HTML element. """

    def __init__(self, tag, attrs=None, children=None):
        """
            Args:
                tag (str):
                attrs (dict)
                children (List[:obj:`.Node`])
        """
        self.tag = tag
        self.attrs = attrs
        self._children = children

    def __call__(self, _shortcut=None, **attrs):
        """ Returns a new node with the same tag but new attributes. """

        def fix_key(k):
            return k.strip('_').replace('_', '-')

        def check_val(v, ttype='class'):
            v = str(v)

            if not v:
                return v

            invalid_chars = ' .,'

            for c in invalid_chars:
                if c in v:
                    raise InvalidAttribute('"%s" is an invalid `%s` value' % (v, ttype))

            return v

        attrs = {fix_key(k): v for k, v in attrs.items()}

        if _shortcut and isinstance(_shortcut, (str, unicode)):
            processed = process_shortcut(_shortcut)

        else:
            processed = {}

        # make a copy of the incoming attributes
        attr_clone = dict(attrs)

        # combine the new and the _shortcut class lists
        cur_classes = attrs.get('class', '').split(' ')
        all_classes = processed.get('class', []) + cur_classes

        # merge the _shortcut attributes and those supplied to the method
        attr_clone.update(processed)

        # re-set the classes on the returned object
        attr_clone['class'] = ' '.join(map(check_val, filter(None, all_classes)))

        id_val = attr_clone.get('id', None)
        if id_val:
            attr_clone['id'] = check_val(str(id_val))

        for k, v in list(attr_clone.items()):
            if not v:
                attr_clone.pop(k, None)

        return Node(self.tag, attr_clone)

    @property
    def children(self):
        return self._children

    def __div__(self, children):
        # python 2 compatibility method
        return self.__truediv__(children)

    def __truediv__(self, children):
        """ Mark ``List[Node]`` or ``Node`` as ``self``'s children.

            Args:
                children (tuple, list)

            Returns:
                self

            Raises:
                LyxException
        """

        if self.children is not None:
            # Block assigning two times the children to a node because
            # doing `a / b / c` is a counter-intuive and an easy-to-miss error
            # that is gonna assign two times the children of `a`
            raise LyxException('Cannot reassign children of `Node` via `/`')

        if self.tag in VOID_TAGS:
            raise LyxException('<%s> can\'t have children nodes' % self.tag)

        if type(children) not in (tuple, list):
            children = (children,)

        self._children = children

        return self

    def __str__(self):
        return render(self)


class RawNode(object):
    """ Node marked as already escaped. """
    def __init__(self, content):
        self.content = content

    def __str__(self):
        return self.content


def raw(content):
    """ Mark a string as already escaped. """
    return RawNode(content)


class _L:
    def __getattr__(self, tag):
        return Node(tag)

L = _L()
