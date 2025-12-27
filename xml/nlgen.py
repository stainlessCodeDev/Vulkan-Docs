import os
import re
import xml.etree.ElementTree as etree
from enum import Enum, auto
from types import SimpleNamespace
from dataclasses import dataclass, field

@dataclass
class BaseObject:
    name: str = field(init=False)
    platform: str = field(init=False)

    def setPlatform(self, platform):
        self.platform = platform

        for child in self:
            child.setPlatform(platform)

    def inferPlatform(self):
        if self.platform == "":
            for child in self:
                child.inferPlatform()
                if child.platform != "":
                    self.platform = child.platform

    def __iter__(self):
        yield from ()

@dataclass
class Typedef(BaseObject):
    type: str = field(init=False)
    nlDecl: str = field(init=False)

@dataclass
class Typealias(BaseObject):
    type: str = field(init=False)
    nlDecl: str = field(init=False)

@dataclass
class EnumMember(BaseObject):
    type: str = field(init=False)
    value: str = field(init=False)
    nlDecl: str = field(init=False)

@dataclass
class Enum(BaseObject):
    type: str = field(init=False)
    node: etree.Element = field(init=False)
    members: dict[str, EnumMember] = field(init=False)
    nlDecl: str = field(init=False)

    def __iter__(self):
        for member in self.members.values():
            yield member

@dataclass
class Funcptr(BaseObject):
    node: etree.Element = field(init=False)
    nlDecl: str = field(init=False)

@dataclass
class StructMember(BaseObject):
    type: str = field(init=False)

@dataclass
class Struct(BaseObject):
    node: etree.Element = field(init=False)
    members: dict[str, StructMember] = field(init=False)
    isUnion: bool = field(init=False)
    nlDecl: str = field(init=False)

    def __iter__(self):
        for member in self.members.values():
            yield member

@dataclass
class CommandArgument(BaseObject):
    type: str = field(init=False)

@dataclass
class Command(BaseObject):
    node: etree.Element = field(init=False)
    args: list[CommandArgument] = field(init=False)
    alias: str = field(init=False)
    nlDecl: str = field(init=False)

    def __iter__(self):
        for arg in self.args:
            yield arg

@dataclass
class Feature(BaseObject):
    node: etree.Element = field(init=False)

@dataclass
class Extension(BaseObject):
    kind: str = field(init=False)
    number: int = field(init=False)
    commandsToLoad: list[Command] = field(init=False)
    nlDecl: str = field(init=False)

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

def fetchTypes(typesNode: etree.Element, typeNameRemap, typealiases, typedefs, structures, funcPtrs):
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
                        alias = Typedef()
                        alias.name = nameNode.text
                        alias.type = typeNameRemap[typealiasNode.text]["name"] # we might need to parse the typedef more properly
                        alias.platform = ""
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
                    alias = Typedef()
                    alias.name = nameNode.text
                    alias.type = typeNameRemap[typealiasNode.text]["name"]
                    alias.platform = ""
                    typedefs[alias.name] = alias
                case "define":
                    pass
                case "enum":
                    if nameAttrib not in typeNameRemap:
                        typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType" : None}

                case "funcpointer":
                    funcPtr = Funcptr()
                    funcPtr.name = nameNode.text
                    funcPtr.node = typeNode
                    funcPtr.platform = ""
                    funcPtrs[funcPtr.name] = funcPtr

                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "group":
                    pass
                case "handle":
                    alias = Typedef()
                    alias.name = nameNode.text
                    alias.type = "void*"
                    alias.platform = ""
                    typedefs[alias.name] = alias

                    typeNameRemap[nameNode.text] = {"name": nameNode.text, "underlyingType": None}

                case "include":
                    pass
                case "struct":
                    structure = Struct()
                    structure.name = nameAttrib
                    structure.members = {}
                    structure.platform = ""
                    structure.isUnion = False
                    structure.node = typeNode
                    structures[structure.name] = structure

                    typeNameRemap[nameAttrib] = {"name": nameAttrib, "underlyingType": None}

                case "union":
                    structure = Struct()
                    structure.name = nameAttrib
                    structure.members = {}
                    structure.platform = ""
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

    enum = Enum()
    enum.name = enumsNode.attrib["name"]
    enum.node = enumsNode
    enum.platform = ""
    enum.members = {}
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

        command = Command()
        command.name = name
        command.type = "" # return type
        command.args = []
        command.node = commandNode
        command.alias = aliasName
        command.platform = ""
        commands[command.name] = command

def fetchFeatures(featureNode, typeNameRemap, features):
    if "api" in featureNode.attrib:
        if "vulkan" not in featureNode.attrib["api"].split(","):
            return
    feature = Feature()
    feature.name = featureNode.attrib["name"]
    feature.node = featureNode
    features[feature.name] = feature

def fetchExtensions(extensionsNode, typeNameRemap, extensions):
    for extensionNode in extensionsNode:
        if extensionNode.tag != "extension":
            continue

        if "supported" in extensionNode.attrib:
            apis = extensionNode.attrib["supported"].split(",")
            if "disabled" in apis:
                continue
            elif "vulkan" not in apis:
                continue

        extension = Extension()
        extension.name = extensionNode.attrib["name"]
        extension.kind = extensionNode.attrib["type"]
        extension.number = int(extensionNode.attrib["number"])
        extension.commandsToLoad = []
        extension.node = extensionNode
        extension.platform = ""

        if "platform" in extensionNode.attrib:
            extension.platform = extensionNode.attrib["platform"]

        extensions[extension.name] = extension

def parseStruct(structure: Struct, typeNameRemap):
    #print("\nstruct {}".format(structure.name))
    for memberNode in structure.node:
        if memberNode.tag != "member":
            continue
        if "api" in memberNode.attrib:
            if "vulkan" not in memberNode.attrib["api"].split(","):
                continue

        member = StructMember()
        member.name = ""
        member.type = ""
        member.platform = ""
        parseVarDecl(memberNode, typeNameRemap, member)

        #print("  {}".format(member))
        structure.members[member.name] = member

    memberDecl = "".join(["\t{} {};\n".format(member.type, member.name) for member in structure])
    if structure.isUnion:
        structure.nlDecl = "union {}\n{{\n{}}}\n".format(structure.name, memberDecl)
    else:
        structure.nlDecl = "struct {}\n{{\n{}}}\n".format(structure.name, memberDecl)

def parseFuncPtr(funcPtr, typeNameRemap):
    state = "return"
    returnType = ""
    arguments = []
    argument = CommandArgument()
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
                argument = CommandArgument()
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
        enum.underlyingType = ""
        enum.name = ""

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
            constant = EnumMember()
            constant.name = constantNode.attrib["name"]
            constant.type = typeNameRemap[constantNode.attrib["type"]]["name"]
            constant.value = constantNode.attrib["value"]
            constant.nlDecl = "const {} = {};\n".format(constant.name, constant.value)
            constant.platform = ""
            constants[constant.name] = constant
        else:
            enumValue = EnumMember()
            enumValue.name = constantNode.attrib["name"] # enum name trimming
            enumValue.platform = ""

            if "bitpos" in constantNode.attrib:
                enumValue.value = "1 << {}".format(constantNode.attrib["bitpos"])
            elif "value" in constantNode.attrib:
                enumValue.value = constantNode.attrib["value"]

            enum.members[enumValue.name] = enumValue

    memberDecl = "".join(["\t{} = {};\n".format(member.name, member.value) for member in enum])
    enum.nlDecl = "enum {} {}\n{{\n{}}}\n".format(enum.name, "as {}".format(enum.underlyingType) if enum.underlyingType else "", memberDecl)

def parseCommand(command, typeNameRemap):
    if command.alias != None:
        return

    for node in command.node:
        if node.tag == "proto":
            parseVarDecl(node, typeNameRemap, command)
        elif node.tag == "param":
            arg = CommandArgument()
            arg.type = ""
            arg.name = ""
            arg.platform = ""
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

    extendsEnum: Enum = enums[typeNameRemap[itemNode.attrib["extends"]]["name"]]
    enumValue = EnumMember()
    enumValue.name = itemNode.attrib["name"] # enum name trimming
    enumValue.platform = ""

    if "bitpos" in itemNode.attrib:
        enumValue.value = "1 << {}".format(itemNode.attrib["bitpos"])
    elif "value" in itemNode.attrib:
        enumValue.value = itemNode.attrib["value"]
    else:
        if "extnumber" in itemNode.attrib:
            extNumber = int(itemNode.attrib["extnumber"]) - 1 # Why is it -1???
        enumValue.value = str((1000000 + extNumber) * 1000 + int(itemNode.attrib["offset"]))

    extendsEnum.members[enumValue.name] = enumValue

def parseFeature(feature, typeNameRemap, enums):
    for requireNode in feature.node:
        for itemNode in requireNode:
            if itemNode.tag == "enum":
                if "extends" in itemNode.attrib:
                    parseEnumExtension(itemNode, typeNameRemap, enums, None)

def parseExtenstion(extension, typeNameRemap, enums, structures, commands):
    for requireNode in extension.node:
        for itemNode in requireNode:
            if itemNode.tag == "enum":
                if "extends" in itemNode.attrib:
                    parseEnumExtension(itemNode, typeNameRemap, enums, extension.number - 1) # Why is it -1???
            elif itemNode.tag == "command":
                command = commands[itemNode.attrib["name"]]
                extension.commandsToLoad.append(command)
                command.setPlatform(extension.platform)
            elif itemNode.tag == "type" and itemNode.attrib["name"] in structures:
                type = structures[itemNode.attrib["name"]]
                type.setPlatform(extension.platform)

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
        command = commandToLoad

        if command.alias != None:
            command = commands[command.alias]

        extension.nlDecl += "    {} = {};\n".format(command.name, procAddr.format(commandToLoad.name))
        pass

    extension.nlDecl += "    return true;\n}\n"

def generateDefsForPlatform(platform, typealiases, typedefs, constants, structures, enums, funcPtrs, commands, extensions):
    filePlatform = platform.capitalize()
    
    with open("vulkan/Vulkan{}.nl".format(filePlatform), "w") as f:
        if platform == "Core":
            platform = ""

        for alias in typealiases.values():
            if alias.platform != platform:
                continue
            f.write("typealias {} {};\n".format(alias.name, alias.type))

        f.write("\n")

        for alias in typedefs.values():
            if alias.platform != platform:
                continue
            f.write("typedef {} {};\n".format(alias.name, alias.type))

        f.write("\n")

        for struct in structures.values():
            if struct.platform != platform:
                continue
            assert struct.nlDecl != None
            f.write(struct.nlDecl)
            f.write("\n")

        for enum in enums.values():
            if enum.platform != platform:
                continue
            assert enum.nlDecl != None
            f.write(enum.nlDecl)
            f.write("\n")

        for const in constants.values():
            if const.platform != platform:
                continue
            assert const.nlDecl != None
            f.write(const.nlDecl)

        f.write("\n")

        for funcPtr in funcPtrs.values():
            if funcPtr.platform != platform:
                continue
            assert funcPtr.nlDecl != None
            f.write(funcPtr.nlDecl)

        f.write("\n")

        for command in commands.values():
            if command.platform != platform:
                continue
            if command.alias != None:
                continue
            assert command.nlDecl != None
            f.write(command.nlDecl)

        for extension in extensions.values():
            if extension.platform != platform:
                continue
            assert command.nlDecl != None
            f.write(extension.nlDecl)

def main():
    treeRoot = etree.parse("vk.xml")
    registryNode = treeRoot.getroot()

    #supportedPlatforms = ["Core", "win32", "xlib", "xlib_xrandr", "xcb", "android"]
    supportedPlatforms = ["Core", "win32"]

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
    objects = {}

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
                fetchExtensions(registryNode, typeNameRemap, extensions)

    for structure in list(structures.values()):
        parseStruct(structure, typeNameRemap)
        objects[structure.name] = structure

    for funcPtr in list(funcPtrs.values()):
        parseFuncPtr(funcPtr, typeNameRemap)
        objects[funcPtr.name] = funcPtr

    for enum in list(enums.values()):
        parseEnum(enum, typeNameRemap, enums, constants, typedefs)
        objects[enum.name] = enum

    for command in list(commands.values()):
        parseCommand(command, typeNameRemap)
        objects[command.name] = command

    for feature in list(features.values()):
        parseFeature(feature, typeNameRemap, enums)

    for extension in list(extensions.values()):
        parseExtenstion(extension, typeNameRemap, enums, structures, commands)

    for object in objects.values():
        object.inferPlatform()

    for platform in supportedPlatforms:
        generateDefsForPlatform(platform, typealiases, typedefs, constants, structures, enums, funcPtrs, commands, extensions)

    print("Generated vulkan module successfully! Totals:")
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
