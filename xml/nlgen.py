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
    COLON = auto()

TOKEN_RE = re.compile(r"""
    \w[\w\d]+  |       # identifiers / keywords
    \d+ |       # digits
    \*  |       # pointer
    \(  | \) |  # parens
    \[  | \] |  # brackets
    ,   |       # comma
    ;   |       # semicolon
    :           # colon
""", re.VERBOSE)

KEYWORDS = [
    "const", "typedef", "struct", "union"
]

def classifyToken(lex):
    if lex == "*":
        return Tok.STAR
    elif lex == ",":
        return Tok.COMMA
    elif lex == ";":
        return Tok.SEMICOLON
    elif lex == ":":
        return Tok.COLON
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
    elif lex.isnumeric():
        return Tok.NUMBER
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
            obj.type = " ".join([obj.type, typeNameRemap[tok.value.strip()]["name"]]).strip()
            continue
        elif tok.kind == "enum":
            obj.type = " ".join([obj.type, tok.value.strip()]).strip()
            continue
        elif tok.kind == "name":
            obj.name = tok.value
            continue
        elif tok.kind in [Tok.STAR, Tok.LBRACKET, Tok.RBRACKET, Tok.NUMBER]:
            obj.type = "".join([obj.type, tok.value]).strip()
        elif tok.kind == Tok.COLON:
            break # We skip bit-fields for now, those structs will be broken!!!!!
        else:
            continue

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
                        alias.type = typeNameRemap[typealiasNode.text]["name"] # we might need to parse the typedef more properly
                        typedefs[alias.name] = alias
                        typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}
                    else:
                        typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "bitmask":
                    # these are enums that are typedef'd for some reason
                    if "requires" in typeNode.attrib:
                        typeNameRemap[typeNode.attrib["requires"]] = {"name": nameNode.text, "underlyingType": typealiasNode.text}
                    elif "bitvalues" in typeNode.attrib:
                        typeNameRemap[typeNode.attrib["bitvalues"]] = {"name": nameNode.text, "underlyingType": typealiasNode.text}
                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": typealiasNode.text}

                    # typedefs that will be removed once an enum shows up, if not it will remain as typedef
                    alias = SimpleNamespace()
                    alias.name = nameNode.text
                    alias.type = typeNameRemap[typealiasNode.text]["name"]
                    typedefs[alias.name] = alias
                case "define":
                    pass
                case "enum":
                    if nameAttrib not in typeNameRemap:
                        typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType" : None}

                case "funcpointer":
                    funcPtr = SimpleNamespace()
                    funcPtr.name = nameNode.text
                    funcPtr.members = []
                    funcPtr.node = typeNode
                    funcPtrs[funcPtr.name] = funcPtr

                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "group":
                    pass
                case "handle":
                    alias = SimpleNamespace()
                    alias.name = nameNode.text
                    alias.type = "void*"
                    typedefs[alias.name] = alias

                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "include":
                    pass
                case "struct":
                    structure = SimpleNamespace()
                    structure.name = nameAttrib
                    structure.members = []
                    structure.isUnion = False
                    structure.node = typeNode
                    structures[structure.name] = structure

                    typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}

                case "union":
                    structure = SimpleNamespace()
                    structure.name = nameAttrib
                    structure.members = []
                    structure.isUnion = True
                    structure.node = typeNode
                    structures[structure.name] = structure

                    typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}
            continue
        elif "requires" in typeNode.attrib:
            if nameAttrib not in typeNameRemap:
                typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}

def fetchEnums(enumsNode, typeNameRemap, enums):
    if "name" not in enumsNode.attrib:
        #WTF
        return

    enum = SimpleNamespace()
    enum.name = enumsNode.attrib["name"]
    enum.node = enumsNode
    enum.members = []
    enums[enum.name] = enum

def fetchCommands(commandsNode, typeNameRemap, commands):
    for commandNode in commandsNode:
        if commandNode.tag != "command":
            continue

        if "api" in commandsNode.attrib:
            if "vulkan" not in commandNode.attrib["api"].split(","):
                continue

        aliasName = None
        name = ""
        if "alias" in commandNode.attrib:
            aliasName = commandNode.attrib["alias"]
            name = commandNode.attrib["name"]
        else:
            name = commandNode.find("proto/name").text

        command = SimpleNamespace()
        command.name = name
        command.type = "" # return type
        command.args = []
        command.node = commandNode
        command.alias = aliasName
        commands[command.name] = command

def fetchFeatures(featureNode, typeNameRemap, features):
    if "api" in featureNode.attrib:
        if "vulkan" not in featureNode.attrib["api"].split(","):
            return
    feature = SimpleNamespace()
    feature.name = featureNode.attrib["name"]
    feature.node = featureNode
    features[feature.name] = feature

def fetchExtensions(extensionsNode, typeNameRemap, extensions, supportedPlatforms):
    for extensionNode in extensionsNode:
        if extensionNode.tag != "extension":
            continue

        if "platform" in extensionNode.attrib:
            if extensionNode.attrib["platform"] not in supportedPlatforms:
                continue

        if "supported" in extensionNode.attrib:
            apis = extensionNode.attrib["supported"].split(",")
            if "disabled" in apis:
                continue
            elif "vulkan" not in apis:
                continue

        extension = SimpleNamespace()
        extension.name = extensionNode.attrib["name"]
        extension.kind = extensionNode.attrib["type"]
        extension.number = int(extensionNode.attrib["number"])
        extension.commandsToLoad = []
        extension.node = extensionNode

        extensions[extension.name] = extension

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
        parseVarDecl(memberNode, typeNameRemap, member)

        #print("  {}".format(member))
        structure.members.append(member)

    memberDecl = "".join(["\t{} {};\n".format(member.type, member.name) for member in structure.members])
    if structure.isUnion:
        structure.nlDecl = "union {}\n{{\n{}}}\n".format(structure.name, memberDecl)
    else:
        structure.nlDecl = "struct {}\n{{\n{}}}\n".format(structure.name, memberDecl)

def parseFuncPtr(funcPtr, typeNameRemap):
    state = "return"
    returnType = ""
    arguments = []
    argument = SimpleNamespace()
    argument.name = ""
    argument.type = ""

    for tok in tokenizeDecl(funcPtr.node):
        if state == "return":
            if tok.kind == Tok.COMMA:
                break
            elif tok.kind == Tok.LPAREN:
                state = "funcptr"
                continue
            elif tok.kind == Tok.KEYWORD:
                continue
            elif tok.kind == "type" or tok.kind == Tok.IDENT and tok.value in typeNameRemap:
                returnType = " ".join([returnType, typeNameRemap[tok.value.strip()]["name"]]).strip()
                continue
            elif tok.kind == "enum":
                returnType = " ".join([returnType, tok.value.strip()]).strip()
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
                argument.type = " ".join([argument.type, typeNameRemap[tok.value.strip()]["name"]]).strip()
                continue
            elif tok.kind == "enum":
                argument.type = " ".join([argument.type, tok.value.strip()]).strip()
                continue
            elif tok.kind == Tok.IDENT:
                argument.name = tok.value
                continue
            elif tok.kind in [Tok.STAR]:
                argument.type = " ".join([argument.type, tok.value]).strip()
                continue
            else:
                continue

    assert argument.type == ""
    assert argument.name == ""

    args = ", ".join(["{} {}".format(arg.type, arg.name) for arg in arguments if arg.name != ""])
    funcPtr.nlDecl = "typealias {} ({}) => {};\n".format(funcPtr.name, args, returnType)

def parseEnum(enum, typeNameRemap, enums, constants, typedefs):
    kind = enum.node.attrib["type"]

    if kind != "constants":
        enums.pop(enum.name)
        enum.underlyingType = typeNameRemap[enum.name]["underlyingType"]
        enum.name = typeNameRemap[enum.name]["name"]
        enums[enum.name] = enum
    else:
        enum.underlyingType = None
        enum.name = None

    for td in list(typedefs.values()):
        if enum.name == td.name:
            typedefs.pop(td.name)

    for constantNode in enum.node:
        if "api" in constantNode.attrib:
            if "vulkan" not in constantNode.attrib["api"].split(","):
                continue

        if constantNode.tag != "enum" or "alias" in constantNode.attrib:
                continue

        if kind == "constants":
            constant = SimpleNamespace()
            constant.name = constantNode.attrib["name"]
            constant.type = typeNameRemap[constantNode.attrib["type"]]["name"]
            constant.value = constantNode.attrib["value"]
            constant.nlDecl = "const {} = {};\n".format(constant.name, constant.value)
            constants[constant.name] = constant
        else:
            enumValue = SimpleNamespace()
            enumValue.name = constantNode.attrib["name"] # enum name trimming

            if "bitpos" in constantNode.attrib:
                enumValue.value = "1 << {}".format(constantNode.attrib["bitpos"])
            elif "value" in constantNode.attrib:
                enumValue.value = constantNode.attrib["value"]

            enum.members.append(enumValue)

    memberDecl = "".join(["\t{} = {};\n".format(member.name, member.value) for member in enum.members])
    enum.nlDecl = "enum {} {}\n{{\n{}}}\n".format(enum.name, "as {}".format(enum.underlyingType) if enum.underlyingType else "", memberDecl)

def parseCommand(command, typeNameRemap):
    if command.alias != None:
        return

    for node in command.node:
        if node.tag == "proto":
            parseVarDecl(node, typeNameRemap, command)
        elif node.tag == "param":
            arg = SimpleNamespace()
            arg.type = ""
            arg.name = ""
            parseVarDecl(node, typeNameRemap, arg)
            command.args.append(arg)
        else:
            continue

    args = ", ".join(["{} {}".format(arg.type, arg.name) for arg in command.args if arg.name != ""])
    command.nlDecl = "global ({}) => {} {} = cast(void*)VulkanAPIStub;\n".format(args, command.type, command.name)
    #if "export" in command.node.attrib:
        #if "vulkan" in command.node.attrib["export"].split(","):
            # these are directly exported from vulkan-1.dll, so we import them via linking, we should trim the vk off of the name [2:]
            #command.nlDecl = "api {} ({}) => {} as \"{}\";\n".format(command.name, args, command.type, command.name)
    #else:
        # these are not exported from loader dll, so we need some more logic here to figure out how to handle these
        # one way is to make them all into global variables and
        #   * make loader procedures per extension (they should be in the xml) that the application can choose to load if the extension is present
        #   * make them into stubs that return an error by default, if they aren't loaded
        # another way is to just emit the procedure typealiases for all of these and
        #command.nlDecl = "typealias {} ({}) => {};".format(command.name, args, command.type)
        #   * make application to create all of the globals and load them manually

def parseEnumExtension(itemNode, typeNameRemap, enums, extNumber):
    if "alias" in itemNode.attrib:
        return

    extendsEnum = enums[typeNameRemap[itemNode.attrib["extends"]]["name"]]
    enumValue = SimpleNamespace()
    enumValue.name = itemNode.attrib["name"] # enum name trimming

    if "bitpos" in itemNode.attrib:
        enumValue.value = "1 << {}".format(itemNode.attrib["bitpos"])
    elif "value" in itemNode.attrib:
        enumValue.value = itemNode.attrib["value"]
    else:
        if "extnumber" in itemNode.attrib:
            extNumber = int(itemNode.attrib["extnumber"]) - 1 # Why is it -1???
        enumValue.value = str((1000000 + extNumber) * 1000 + int(itemNode.attrib["offset"]))

    extendsEnum.members.append(enumValue)

def parseFeature(feature, typeNameRemap, enums):
    for requireNode in feature.node:
        for itemNode in requireNode:
            if itemNode.tag == "enum":
                if "extends" in itemNode.attrib:
                    parseEnumExtension(itemNode, typeNameRemap, enums, None)

def parseExtenstion(extension, typeNameRemap, enums, commands):
    for requireNode in extension.node:
        for itemNode in requireNode:
            if itemNode.tag == "enum":
                if "extends" in itemNode.attrib:
                    parseEnumExtension(itemNode, typeNameRemap, enums, extension.number - 1) # Why is it -1???
            elif itemNode.tag == "command":
                extension.commandsToLoad.append(itemNode.attrib["name"])

    extension.nlDecl = ""

    if len(extension.commandsToLoad) == 0:
        return

    context = "VkInstance instance"
    procAddr = "vkGetInstanceProcAddr(instance, \"{}\")"
    if extension.kind == "device":
        context = "VkDevice device"
        procAddr = "vkGetDeviceProcAddr(device, \"{}\")"

    extension.nlDecl = """
proc Load{}({}) => bool
{{
"""
    # maybe even we can do a check for extension existancce or something,
    # need to learn a bit more about extensions and if there anything special needs to be done to load one
    extension.nlDecl = extension.nlDecl.format(extension.name, context)

    for commandToLoad in extension.commandsToLoad:
        command = commands[commandToLoad]

        if command.alias != None:
            command = commands[command.alias]

        extension.nlDecl += "    {} = {};\n".format(command.name, procAddr.format(commandToLoad))
        pass

    extension.nlDecl += "    return true;\n}\n"

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
        "size_t": {"name" : "uptr", "underlyingType": None},
        "ptrdiff_t": {"name": "iptr", "underlyingType": None},
    }

    typealiases = {}
    typedefs = {}
    structures = {}
    funcPtrs = {}
    constants = {}
    enums = {}
    commands = {}
    features = {} # Features seems to be a very very messy!
    extensions = {}

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
            case "extensions":
                fetchExtensions(registryNode, typeNameRemap, extensions, supportedPlatforms)

    for structure in list(structures.values()):
        parseStruct(structure, typeNameRemap)

    for funcPtr in list(funcPtrs.values()):
        parseFuncPtr(funcPtr, typeNameRemap)

    for enum in list(enums.values()):
        parseEnum(enum, typeNameRemap, enums, constants, typedefs)

    for command in list(commands.values()):
        parseCommand(command, typeNameRemap)

    for feature in list(features.values()):
        parseFeature(feature, typeNameRemap, enums)

    for extension in list(extensions.values()):
        parseExtenstion(extension, typeNameRemap, enums, commands)

    with open("vulkan/VulkanDefs.nl", "w") as f:
        for alias in typealiases.values():
            f.write("typealias {} {};\n".format(alias.name, alias.type))

        f.write("\n")

        for alias in typedefs.values():
            f.write("typedef {} {};\n".format(alias.name, alias.type))

        f.write("\n")

        for struct in structures.values():
            assert struct.nlDecl != None
            f.write(struct.nlDecl)
            f.write("\n")

        for enum in enums.values():
            assert enum.nlDecl != None
            f.write(enum.nlDecl)
            f.write("\n")

        for const in constants.values():
            assert const.nlDecl != None
            f.write(const.nlDecl)

        f.write("\n")

        for funcPtr in funcPtrs.values():
            assert funcPtr.nlDecl != None
            f.write(funcPtr.nlDecl)

        f.write("\n")

        for command in commands.values():
            if command.alias != None:
                continue
            assert command.nlDecl != None
            f.write(command.nlDecl)

        for extension in extensions.values():
            assert command.nlDecl != None
            f.write(extension.nlDecl)

    print("Generated vulkan.nl:")
    print("  Typealiases: {}".format(len(typealiases)))
    print("  Typedefs: {}".format(len(typedefs)))
    print("  Structs: {}".format(len(structures)))
    print("  Enums: {}".format(len(enums)))
    print("  Constants: {}".format(len(constants)))
    print("  Funcptrs: {}".format(len(funcPtrs)))
    print("  Commands: {}".format(len(commands)))
    print("  Extensions: {}".format(len(extensions)))

if __name__ == '__main__':
    main()
