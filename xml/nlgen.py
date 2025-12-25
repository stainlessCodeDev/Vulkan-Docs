import os
import re
import xml.etree.ElementTree as etree
from enum import Enum, auto
from types import SimpleNamespace

def iterMixed(elem):
    if elem.text:
        yield elem.text

    for child in elem:
        yield child
        if child.tail:
            yield child.tail

class Tok(Enum):
    IDENT = auto()
    KEYWORD = auto()
    STAR = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    SEMICOLON = auto()
    NUMBER = auto()

TOKEN_RE = re.compile(r"""
    \w[\w\d]+  |       # identifiers / keywords
    \d+ |       # digits
    \*  |       # pointer
    \(  | \) |  # parens
    \[  | \] |  # brackets
    ,           # comma
    ;           # semicolon
""", re.VERBOSE)

KEYWORDS 
[
    "const", "typedef"
]

def classifyToken(lex):
    if lex == "*":
        return Tok.STAR
    elif lex == ",":
        return Tok.COMMA
    elif lex == ";":
        return Tok.SEMICOLON
    elif lex == "(":
        return Tok.LPAREN
    elif lex == ")":
        return Tok.RPAREN
    elif lex == "[":
        return Tok.LBRACKET
    elif lex == "]":
        return Tok.RBRACKET
    elif lex in KEYWORDS:
        return Tok.KEYWORD
    else:
        return Tok.IDENT

def tokenizeDecl(elem):
    for part in iterMixed(elem):
        if isinstance(part, str):
            for tok in TOKEN_RE.findall(part):
                yield SimpleNamespace(kind=classifyToken(tok), value=tok)
        else:
            # XML element (name, type, etc.)
            yield SimpleNamespace(kind=part.tag, value=part.text)

def parseVarDecl(objNode, typeNameRemap, obj):
    for tok in tokenizeDecl(objNode):
        if tok.kind == Tok.COMMA:
            break
        elif tok.kind == Tok.RPAREN:
            break
        elif tok.kind == Tok.KEYWORD:
            continue
        elif tok.kind == "type":
            obj.type = " ".join([obj.type, typeNameRemap[node.text.strip()]["name"]]).strip()
            continue
        elif tok.kind == "enum":
            obj.type = " ".join([obj.type, node.text.strip()]).strip()
            continue
        elif tok.kind == "name":
            obj.name = node.text
        else:
            obj.type = " ".join([obj.type, tok.value]).strip()

def fetchTypes(typesNode, typeNameRemap, typealiases, typedefs, structures, funcPtrs):
    for typeNode in typesNode:
        if typeNode.tag != "type":
            continue

        if "api" in typeNode.attrib:
            if "vulkan" not in typeNode.attrib["api"].split(","):
                continue

        nameNode = typeNode.find("name")
        typealiasNode = typeNode.find("type")
        nameAttrib = typeNode.attrib.get("name")

        if "alias" in typeNode.attrib:
            typeNameRemap[nameAttrib] = {"name": typeNode.attrib["alias"], "underlyingType": None}
            continue
        
        if "category" in typeNode.attrib:
            match typeNode.attrib["category"]:
                case "basetype":
                    if "typedef" in typeNode.text and nameNode != None and typealiasNode != None:
                        alias = SimpleNamespace()
                        alias.name = nameNode.text
                        alias.type = typealiasNode.text # we might need to parse the typedef more properly
                        typedefs.append(alias)
                        typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}
                    else:
                        typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "bitmask":
                    # these are enums that are typedef'd for some reason
                    if "requires" in typeNode.attrib:
                        typeNameRemap[typeNode.attrib["requires"]] = {"name": nameNode.text, "underlyingType": typealiasNode.text}
                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": typealiasNode.text}

                case "define":
                    pass
                case "enum":
                    if nameAttrib not in typeNameRemap:
                        typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType" : None}

                case "funcpointer":
                    funcPtr = SimpleNamespace()
                    funcPtr.name = nameAttrib
                    funcPtr.members = []
                    funcPtr.node = typeNode
                    funcPtrs.append(funcPtr)

                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "group":
                    pass
                case "handle":
                    alias = SimpleNamespace()
                    alias.name = nameNode.text
                    alias.type = typealiasNode.text
                    typedefs.append(alias)

                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "include":
                    pass
                case "struct":
                    structure = SimpleNamespace()
                    structure.name = nameAttrib
                    structure.members = []
                    structure.isUnion = False
                    structure.node = typeNode
                    structures.append(structure)

                    typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}

                case "union":
                    structure = SimpleNamespace()
                    structure.name = nameAttrib
                    structure.members = []
                    structure.isUnion = True
                    structure.node = typeNode
                    structures.append(structure)

                    typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}
            continue
        elif "requires" in typeNode.attrib:
            typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}

def fetchEnums(enumsNode, typeNameRemap, enums):
    if "name" not in enumsNode.attrib:
        #WTF
        return
    
    enum = SimpleNamespace()
    enum.name = enumsNode.attrib["name"]
    enum.node = enumsNode
    enum.members = []
    enums.append(enum)

def fetchCommands(commandsNode, typeNameRemap, commands):
    for commandNode in commandsNode:
        if commandsNode.tag != "command":
            continue
        
        if "api" in commandsNode.attrib:
            if "vulkan" not in commandNode.attrib["api"].split(","):
                continue

        if "alias" in commandNode.attrib:
            continue

        command = SimpleNamespace()
        command.name = ""
        command.type = "" # return type
        command.params = []
        command.node = commandNode
        commands.append(command)

def fetchFeatures(featuresNode, typeNameRemap, features):
    pass

def parseStruct(structure, typeNameRemap):
    #print("\nstruct {}".format(structure.name))
    for memberNode in structure.node:
        if memberNode.tag != "member":
            continue
        if "api" in memberNode.attrib:
            if "vulkan" not in memberNode.attrib["api"].split(","):
                continue
        
        member = SimpleNamespace()
        member.name = ""
        member.type = ""
        parseVarDecl(node, typeNameRemap, member)

        #print("  {}".format(member))
        structure.members.append(member)
    
    memberDecl = ";\n".join(["{} {}".format(member.type, member.name) for member in structure.members])
    if structure.isUnion:
        structure.nlDecl = "union {}\n{{\n{}}}".format(structure.name, memberDecl)
    else:
        structure.nlDecl = "struct {}\n{{\n{}}}".format(structure.name, memberDecl)

def parseFuncPtr(funcPtr, typeNameRemap):
    state = "return"
    returnType = ""
    arguments = []
    argument = SimpleNamespace()
    argument.name = ""
    argument.type = ""
    for tok in tokenizeDecl(funcPtr):
        if state == "return":
            if tok.kind == Tok.COMMA:
                break
            elif tok.kind == Tok.LPAREN:
                state = "funcptr"
                continue
            elif tok.kind == Tok.KEYWORD:
                continue
            elif tok.kind == "type" or tok.kind == Tok.IDENT and tok.value in typeNameRemap:
                returnType = " ".join([returnType, typeNameRemap[node.text.strip()]["name"]]).strip()
                continue
            elif tok.kind == "enum":
                returnType = " ".join([returnType, node.text.strip()]).strip()
                continue
            else:
                returnType = " ".join([returnType, tok.value]).strip()
                continue
        elif state == "funcptr":
            if tok.kind == "name":
                funcPtr.name = tok.value
            elif tok.kind == Tok.LPAREN:
                state = "arguments"
                continue
            else:
                continue
        elif state == "arguments":
            if tok.kind in [Tok.COMMA, Tok.SEMICOLON]:
                arguments.append(argument)
                argument = SimpleNamespace()
                argument.name = ""
                argument.type = ""
            elif tok.kind == Tok.KEYWORD:
                continue
            elif tok.kind == "type" or tok.kind == Tok.IDENT and tok.value in typeNameRemap:
                argument.type = " ".join([argument.type, typeNameRemap[node.text.strip()]["name"]]).strip()
                continue
            elif tok.kind == "enum":
                argument.type = " ".join([argument.type, node.text.strip()]).strip()
                continue
            elif tok.kind == Tok.IDENT:
                argument.name = tok.value
                continue
            else:
                argument.type = " ".join([argument.type, tok.value]).strip()
                continue

    assert argument.type == ""
    assert argument.name == ""

    funcPtr.nlDecl = "typealias {} ({}) => {};".format(funcPtr.name, ", ".join(["{} {}".format(arg.type, arg.name) for arg in arguments]), returnType)

def parseEnum(enum, typeNameRemap, constants):
    kind = enum.node.attrib["type"]

    enum.underlyingType = typeNameRemap[enum.name]["underlyingType"]
    enum.name = typeNameRemap[enum.name]["name"]

    for constantNode in enum.node:
        if "api" in constantNode.attrib:
            if "vulkan" not in constantNode.attrib["api"].split(","):
                continue

        if constantNode.tag != "enum":
                continue

        if kind == "constants":
            constant = SimpleNamespace()
            constant.name = constantNode.attrib["name"]
            constant.type = typeNameRemap[constantNode.attrib["type"]]["name"]
            constant.value = constantNode.attrib["value"]

            constants.append(constant)
        else:
            enumValue = SimpleNamespace()
            enumValue.name = constantNode.attrib["name"] # enum name trimming
            enumValue.value = constantNode.attrib["value"]

            if "bitpos" in constantNode.attrib:
                enumValue.value = "1 << {}".format(constantNode.attrib["bitpos"])
            elif "value" in constantNode.attrib:
                enumValue.value = constantNode.attrib["value"]

            enum.members.append(enumValue)

    memberDecl = ",\n".join(["{} = {}".format(member.name, member.value) for member in enum.members])
    enum.nlDecl = "enum {} {}\n{{\n{}}}".format(enum.name, "as {}".format(enum.underlyingType) if enum.underlyingType else "", memberDecl)

def parseCommand(command, typeNameRemap):
    for node in command.node:
        if node.tag == "proto":
            parseDecl(node, typeNameRemap, command)
        elif node.tag == "param":
            arg = SimpleNamespace()
            parseDecl(node, typeNameRemap, arg)
            command.params.append(arg)
        else:
            continue

    args = ", ".join(["{} {}".format(arg.type, arg.name) for arg in command.params])
    if "export" in command.node.attrib:
        if "vulkan" in command.node.attrib["export"]:
            # these are directly exported from vulkan-1.dll, so we import them via linking, we should trim the vk off of the name [2:]
            funcPtr.nlDecl = "api {} ({}) => {} as \"{}\";".format(command.name, args, returnType, command.name)
    else:
        # these are not exported from loader dll, so we need some more logic here to figure out how to handle these
        # one way is to make them all into global variables and either
        funcPtr.nlDecl = "global {} ({}) => {};".format(command.name, args, returnType)
        #   * make the application load them manually
        #   * or make loader procedures per extension (they should be in the xml) that the application can choose to load if the extension is present
        #   * or make them into stubs that return an error by default, if they aren't loaded
        # another way is to just emit the procedure typealiases for all of these and
        #   * make application to create all of the globals and load them manually
        pass

def main():
    treeRoot = etree.parse("vk.xml")
    registryNode = treeRoot.getroot()

    #supportedPlatforms = ["win32", "xlib", "xlib_xrandr", "xcb", "android"]
    supportedPlatforms = ["win32"]

    #TODO: Detect if the platform is defined in the xml
    # and grab the protect attribute for all of them if we actually need it

    typeNameRemap = {
        "void": {"name" : "void", "underlyingType": None},
        "char": {"name" : "u8", "underlyingType": None},
        "float": {"name" : "f32", "underlyingType": None},
        "double": {"name" : "f64", "underlyingType": None},
        "int": {"name" : "i32", "underlyingType": None},
        "int8_t": {"name" : "i8", "underlyingType": None},
        "int16_t": {"name" : "i16", "underlyingType": None},
        "int32_t": {"name" : "i32", "underlyingType": None},
        "int64_t": {"name" : "i64", "underlyingType": None},
        "uint8_t": {"name" : "u8", "underlyingType": None},
        "uint16_t": {"name" : "u16", "underlyingType": None},
        "uint32_t": {"name" : "u32", "underlyingType": None},
        "uint64_t": {"name" : "u64", "underlyingType": None},
        "size_t": {"name" : "uintptr", "underlyingType": None},
    }

    typealiases = []
    typedefs = []
    structures = []
    funcPtrs = []
    constants = []
    enums = []
    commands = []
    features = []

    for registryNode in registryNode:
        match registryNode.tag:
            case "types":
                fetchTypes(registryNode, typeNameRemap, typealiases, typedefs, structures, funcPtrs)
            case "enums":      
                fetchEnums(registryNode, typeNameRemap, enums)
            case "commands":
                fetchCommands(registryNode, typeNameRemap, commands)
            case "feature":
                fetchFeatures(registryNode, typeNameRemap, features)

    for structure in structures:
        parseStruct(structure, typeNameRemap)

    for funcPtr in funcPtrs:
        parseFuncPtr(funcPtr, typeNameRemap)
    
    for enum in enums:
        parseEnum(enum, typeNameRemap, constants)
    
    for command in commands:
        parseCommand(command, typeNameRemap)
    



if __name__ == '__main__':
    main()