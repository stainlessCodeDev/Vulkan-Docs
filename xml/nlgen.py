import os
import re
import xml.etree.ElementTree as etree
from enum import Enum, auto
from types import SimpleNamespace
from dataclasses import dataclass, field

@dataclass
class GenOpts:
    api: str = field(default=None)
    platform: str = field(default=None)
    nameFilter: list[str] = field(default_factory=list[str])

    def noFilter(self):
        return GenOpts(api=self.api, platform=self.platform)

@dataclass
class BaseObject:
    name: str = field(default="", init=False)
    type: str = field(default=None, init=False)
    node: etree.Element = field(default=None, init=False)

    platform: str = field(default="", init=False)
    enabledCounter: int = field(default=0, init=False)
    apis: list[str] = field(default_factory=list[str], init=False)

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
    
    def isDisabled(self, genOpts = None):
        if genOpts == None:
            genOpts = GenOpts()

        if genOpts.api != None and len(self.apis) > 0 and genOpts.api not in self.apis:
            return True
        elif genOpts.platform != None and self.platform != genOpts.platform:
            return True
        elif self.enabledCounter < 0:
            return True
        else:
            for filter in genOpts.nameFilter:
                if filter.casefold() in self.name.casefold():
                    return True
            return False

    def setDisabled(self, disable):
        if disable:
            self.enabledCounter -= 1
        else:
            self.enabledCounter += 1

    def toDecl(self, genOpts):
        pass

    def __iter__(self):
        yield from ()

@dataclass
class Typedef(BaseObject):
    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        return "typedef {} {};\n".format(self.name, self.type)

@dataclass
class Typealias(BaseObject):
    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        return "typealias {} {};\n".format(self.name, self.type)

@dataclass
class EnumMember(BaseObject):
    value: str = field(default=None, init=False)
    isConst: bool = field(default=False, init=False)

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        value = self.value.lower().translate(str.maketrans("", "", "FfUuLl"))

        if self.isConst:
            return "const {} = {};\n".format(self.name, value if self.type == None else "cast({}){}".format(self.type, value))
        else:
            return "    {} = {};\n".format(self.name, self.value)

@dataclass
class Enum(BaseObject):
    members: dict[str, EnumMember] = field(default_factory=dict[str, EnumMember], init=False)

    def __iter__(self):
        for member in self.members.values():
            yield member

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        memberDecl = "".join([m.toDecl(genOpts) for m in self])
        return "enum {}{}\n{{\n{}}}\n\n".format(self.name, " as {}".format(self.type) if self.type else "", memberDecl)

@dataclass
class Funcptr(BaseObject):
    arguments: list[str] = field(default_factory=list[str], init=False)

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        args = ", ".join(["{} {}".format(arg.type, arg.name) for arg in self.arguments if arg.name != ""])
        return "typealias {} ({}) => {};\n".format(self.name, args, self.type)

@dataclass
class StructMember(BaseObject):
    def toDecl(self, genOpts):
        if self.isDisabled(genOpts.noFilter()):
            return ""
        return "    {} {};\n".format(self.type, self.name)

@dataclass
class Struct(BaseObject):
    members: dict[str, StructMember] = field(default_factory=dict[str, StructMember], init=False)
    isUnion: bool = field(default=False, init=False)

    def __iter__(self):
        for member in self.members.values():
            yield member

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        memberDecl = "".join([member.toDecl(genOpts) for member in self])

        if self.isUnion:
            return "union {}\n{{\n{}}}\n\n".format(self.name, memberDecl)
        else:
            return "struct {}\n{{\n{}}}\n\n".format(self.name, memberDecl)

@dataclass
class CommandArgument(BaseObject):
    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if self.name == "":
            return ""

        return "{} {}".format(self.type, self.name)

@dataclass
class Command(BaseObject):
    args: list[CommandArgument] = field(default_factory=list[CommandArgument], init=False)
    alias: str = field(default=None, init=False)
    export: list[str] = field(default_factory=list[str], init=False)

    def __iter__(self):
        for arg in self.args:
            yield arg

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if self.alias != None:
            return ""

        args = ", ".join(a for a in [arg.toDecl(genOpts) for arg in self] if a)

        # we disabled this, because even the loader docs says that the best strategy is to get addresses directly and store them yourself to get the best performance
        if False and api != None and api in self.export:
            # these are directly exported from vulkan-1.dll, so we import them via linking, we should trim the vk off of the name [2:]
            return "api {} ({}) => {} as \"{}\";\n".format(self.name, args, self.type, self.name)
        else:
            # these are not exported from loader dll, so we need some more logic here to figure out how to handle these
            # one way is to make them all into global variables and
            #   * make loader procedures per extension (they should be in the xml) that the application can choose to load if the extension is present
            #   * make them into stubs that return an error by default, if they aren't loaded
            # another way is to just emit the procedure typealiases for all of these and
            #command.nlDecl = "typealias {} ({}) => {};".format(command.name, args, command.type)
            #   * make application to create all of the globals and load them manually
            return "global ({}) => {} {} = cast(void*)&VulkanAPIStub;\n".format(args, self.type, self.name)

@dataclass
class Feature(BaseObject):
    pass

@dataclass
class Extension(BaseObject):
    kind: str = field(default=None, init=False)
    number: int = field(default=None, init=False)
    commandsToLoad: list[Command] = field(default_factory=list[Command], init=False)

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if len(self.commandsToLoad) == 0:
            return ""

        context = "VkInstance instance"
        procAddr = "vkGetInstanceProcAddr(instance, \"{}\")"
        if self.kind == "device":
            context = "VkDevice device"
            procAddr = "vkGetDeviceProcAddr(device, \"{}\")"

        result = """proc Load{}({}) => bool
{{
"""
        # maybe even we can do a check for extension existancce or something,
        # need to learn a bit more about extensions and if there anything special needs to be done to load one
        result = result.format(self.name, context)

        for commandToLoad in self.commandsToLoad:
            command = commandToLoad

            if command.alias != None:
                command = command.alias

            result += "    {} = cast(void*) {};\n".format(command.name, procAddr.format(commandToLoad.name))
            pass

        return result + "    return true;\n}\n\n"

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
            yield SimpleNamespace(kind=part.tag, value=part.text.strip())

def parseVarDecl(objNode, typeNameRemap, obj):
    obj.type = ""
    for tok in tokenizeDecl(objNode):
        if tok.kind == Tok.COMMA:
            break
        elif tok.kind == Tok.RPAREN:
            break
        elif tok.kind == Tok.KEYWORD:
            continue
        elif tok.kind == "type":
            obj.type += " " + typeNameRemap[tok.value]
            continue
        elif tok.kind == "enum":
            obj.type += " " + tok.value
            continue
        elif tok.kind == "name":
            obj.name = tok.value
            continue
        elif tok.kind in [Tok.STAR, Tok.LBRACKET, Tok.RBRACKET, Tok.NUMBER]:
            obj.type += tok.value
        elif tok.kind == Tok.COLON:
            break # We skip bit-fields for now, those structs will be broken!!!!!
        else:
            continue

    obj.type = obj.type.strip()

def fetchTypes(typesNode: etree.Element, typeNameRemap, typealiases, typedefs, structures, funcPtrs):
    for typeNode in typesNode:
        if typeNode.tag != "type":
            continue

        apis = []

        if "api" in typeNode.attrib:
            apis = typeNode.attrib["api"].split(",")

        nameNode = typeNode.find("name")
        nameAttrib = typeNode.attrib.get("name")
        aliasName = typeNode.attrib.get("alias")

        if aliasName != None:
            alias = Typealias()
            alias.name = nameAttrib
            alias.type = aliasName
            alias.apis = apis
            alias.node = typeNode
            typealiases[alias.name] = alias
            typeNameRemap[nameAttrib] = aliasName
            continue

        if "category" in typeNode.attrib:
            match typeNode.attrib["category"]:
                case "basetype":
                    alias = Typedef()
                    alias.name = nameNode.text
                    alias.apis = apis
                    alias.node = typeNode

                    typedefs[alias.name] = alias
                    typeNameRemap[nameNode.text] = nameNode.text

                case "bitmask":
                    # these are enums that are typedef'd for some reason
                    # typedefs that will be removed once an enum shows up, if not it will remain as typedef
                    alias = Typedef()
                    alias.name = nameNode.text
                    alias.apis = apis
                    alias.node = typeNode

                    typedefs[alias.name] = alias

                    if "requires" in typeNode.attrib:
                        typeNameRemap[typeNode.attrib["requires"]] = alias.name
                    elif "bitvalues" in typeNode.attrib:
                        typeNameRemap[typeNode.attrib["bitvalues"]] = alias.name

                    typeNameRemap[alias.name] = alias.name
                case "define":
                    pass
                case "enum":
                    if nameAttrib not in typeNameRemap:
                        typeNameRemap[nameAttrib] = nameAttrib

                case "funcpointer":
                    funcPtr = Funcptr()
                    funcPtr.name = nameNode.text
                    funcPtr.node = typeNode
                    funcPtr.apis = apis
                    funcPtrs[funcPtr.name] = funcPtr

                    typeNameRemap[nameNode.text] = nameNode.text

                case "group":
                    pass
                case "handle":
                    alias = Typedef()
                    alias.name = nameNode.text
                    alias.type = "void*"
                    alias.apis = apis
                    alias.node = typeNode
                    typedefs[alias.name] = alias

                    typeNameRemap[nameNode.text] = nameNode.text

                case "include":
                    pass
                case "struct":
                    structure = Struct()
                    structure.name = nameAttrib
                    structure.node = typeNode
                    structure.apis = apis
                    structures[structure.name] = structure

                    typeNameRemap[nameAttrib] = nameAttrib

                case "union":
                    structure = Struct()
                    structure.name = nameAttrib
                    structure.isUnion = True
                    structure.node = typeNode
                    structure.apis = apis
                    structures[structure.name] = structure

                    typeNameRemap[nameAttrib] = nameAttrib
            continue
        elif "requires" in typeNode.attrib:
            if nameAttrib not in typeNameRemap:
                typeNameRemap[nameAttrib] = nameAttrib

def fetchEnums(enumsNode, typeNameRemap, enums):
    if "name" not in enumsNode.attrib:
        #WTF
        return

    enum = Enum()
    enum.name = enumsNode.attrib["name"]
    enum.node = enumsNode

    if "api" in enumsNode.attrib:
        enum.apis = enumsNode.attrib["api"].split(",")

    enums[enum.name] = enum

def fetchCommands(commandsNode, typeNameRemap, commands):
    for commandNode in commandsNode:
        if commandNode.tag != "command":
            continue

        command = Command()
        command.node = commandNode

        if "api" in commandsNode.attrib:
            command.apis = commandNode.attrib["api"].split(",")

        if "alias" in commandNode.attrib:
            command.alias = commandNode.attrib["alias"]
            command.name = commandNode.attrib["name"]
        else:
            command.name = commandNode.find("proto/name").text

        commands[command.name] = command

def fetchFeatures(featureNode, typeNameRemap, features):
    feature = Feature()
    feature.name = featureNode.attrib["name"]
    feature.node = featureNode

    if "api" in featureNode.attrib:
        feature.apis = featureNode.attrib["api"].split(",")

    features[feature.name] = feature

def fetchExtensions(extensionsNode, typeNameRemap, extensions):
    for extensionNode in extensionsNode:
        if extensionNode.tag != "extension":
            continue

        extension = Extension()
        extension.name = extensionNode.attrib["name"]
        extension.number = int(extensionNode.attrib["number"])
        extension.node = extensionNode

        if "type" in extensionNode.attrib:
            extension.kind = extensionNode.attrib["type"]

        if "platform" in extensionNode.attrib:
            extension.platform = extensionNode.attrib["platform"]

        if "supported" in extensionNode.attrib:
            extension.apis = extensionNode.attrib["supported"].split(",")
            if "disabled" in extension.apis:
                extension.setDisabled(True)

        extensions[extension.name] = extension

def parseAlias(alias, typeNameRemap):
    if alias.node.text and "typedef" in alias.node.text:
        parseVarDecl(alias.node, typeNameRemap, alias)

    if alias.type in typeNameRemap:
        alias.type = typeNameRemap[alias.type]

def parseStruct(structure: Struct, typeNameRemap):
    for memberNode in structure.node:
        if memberNode.tag != "member":
            continue

        member = StructMember()

        if "api" in memberNode.attrib:
            member.apis = memberNode.attrib["api"].split(",")

        parseVarDecl(memberNode, typeNameRemap, member)
        structure.members[member.name] = member

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
                returnType = " ".join([returnType, typeNameRemap[tok.value.strip()]]).strip()
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
                argument.type = " ".join([argument.type, typeNameRemap[tok.value.strip()]]).strip()
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
    funcPtr.arguments = arguments
    funcPtr.type = returnType

def parseEnum(enum, typeNameRemap, enums, constants, typedefs):
    kind = enum.node.attrib["type"]

    if kind != "constants":
        enums.pop(enum.name)

        if enum.name in typedefs:
            alias = typedefs[enum.name]
            typedefs.pop(enum.name)
            enum.type = typeNameRemap[alias.type]

        enum.name = typeNameRemap[enum.name]
        enums[enum.name] = enum
    else:
        enums.pop(enum.name)
        enum.type = ""
        enum.name = ""

    for constantNode in enum.node:
        if constantNode.tag != "enum":
            continue

        enumValue = EnumMember()
        enumValue.name = constantNode.attrib["name"] # enum name trimming

        if "api" in constantNode.attrib:
            enumValue.apis = constantNode.attrib["api"].split(",")

        if "bitpos" in constantNode.attrib:
            enumValue.value = "1 << {}".format(constantNode.attrib["bitpos"])
        elif "value" in constantNode.attrib:
            enumValue.value = constantNode.attrib["value"]
        elif "alias" in constantNode.attrib:
            enumValue.value = constantNode.attrib["alias"]

        if kind == "constants":
            enumValue.isConst = True
            enumValue.type = typeNameRemap[constantNode.attrib["type"]]
            constants[enumValue.name] = enumValue
        else:
            enum.members[enumValue.name] = enumValue

def parseCommand(command, typeNameRemap, commands):
    if command.alias != None:
        command.alias = commands[command.alias]
        return

    for node in command.node:
        if node.tag == "proto":
            parseVarDecl(node, typeNameRemap, command)
        elif node.tag == "param":
            arg = CommandArgument()

            if "api" in node.attrib:
                arg.apis = node.attrib["api"].split(",")

            parseVarDecl(node, typeNameRemap, arg)
            command.args.append(arg)
        else:
            continue

    if "export" in command.node.attrib:
        command.export = command.node.attrib["export"].split(",")

def parseEnumExtension(itemNode, name, typeNameRemap, enums, extNumber):
    if "alias" in itemNode.attrib:
        return

    extendsEnum: Enum = enums[typeNameRemap[itemNode.attrib["extends"]]]
    enumValue = EnumMember()
    enumValue.name = name

    if "bitpos" in itemNode.attrib:
        enumValue.value = "1 << {}".format(itemNode.attrib["bitpos"])
    elif "value" in itemNode.attrib:
        enumValue.value = itemNode.attrib["value"]
    elif "alias" in itemNode.attrib:
        enumValue.value = itemNode.attrib["alias"]
    else:
        if "extnumber" in itemNode.attrib:
            extNumber = int(itemNode.attrib["extnumber"]) # Why is it -1???
        enumValue.value = str((1000000 + extNumber - 1) * 1000 + int(itemNode.attrib["offset"]))

    extendsEnum.members[enumValue.name] = enumValue

def parseFeature(feature, typeNameRemap, enums):
    for requireNode in feature.node:
        for itemNode in requireNode:
            if itemNode.tag == "enum":
                if "extends" in itemNode.attrib:
                    name = itemNode.attrib["name"] # enum name trimming
                    parseEnumExtension(itemNode, name, typeNameRemap, enums, None)

def parseExtenstion(extension, typeNameRemap, enums, structures, commands, objects):
    for requireNode in extension.node:
        for itemNode in requireNode:
            name = None
            if "name" in itemNode.attrib:
                name = itemNode.attrib["name"] # enum name trimming

            if itemNode.tag == "enum":
                if "extends" in itemNode.attrib:
                    parseEnumExtension(itemNode, name, typeNameRemap, enums, extension.number)
            elif itemNode.tag == "command":
                command = commands[name]
                extension.commandsToLoad.append(command)
                command.setPlatform(extension.platform)
                command.setDisabled(extension.isDisabled())
            elif itemNode.tag == "type":
                type = objects[typeNameRemap[name]]
                type.setPlatform(extension.platform)
                type.setDisabled(extension.isDisabled())

def generateDefsForPlatform(genOpts, typealiases, typedefs, constants, structures, enums, funcPtrs, commands, extensions, objects):
    filePlatform = genOpts.platform.capitalize()

    with open("vulkan/Vulkan{}.nl".format(filePlatform), "w") as f:
        if genOpts.platform == "Core":
            genOpts.platform = ""

        for alias in typealiases.values():
            if alias.type in objects:
                if objects[alias.type].isDisabled(genOpts):
                    continue

            f.write(alias.toDecl(genOpts))

        f.write("\n")

        for alias in typedefs.values():
            f.write(alias.toDecl(genOpts))

        f.write("\n")

        for struct in structures.values():
            f.write(struct.toDecl(genOpts))

        for enum in enums.values():
            f.write(enum.toDecl(genOpts))

        for const in constants.values():
            f.write(const.toDecl(genOpts))

        f.write("\n")

        for funcPtr in funcPtrs.values():
            f.write(funcPtr.toDecl(genOpts))

        f.write("\n")

        for command in commands.values():
            f.write(command.toDecl(genOpts))

        f.write("\n")

        for extension in extensions.values():
            f.write(extension.toDecl(genOpts))

def main():
    treeRoot = etree.parse("vk.xml")
    registryNode = treeRoot.getroot()

    #supportedPlatforms = ["Core", "win32", "xlib", "xlib_xrandr", "xcb", "android"]
    supportedPlatforms = ["Core", "win32"]

    #TODO: Detect if the platform is defined in the xml
    # and grab the protect attribute for all of them if we actually need it

    typeNameRemap = {
        "void":      "void",
        "char":      "u8",
        "float":     "f32",
        "double":    "f64",
        "int":       "i32",
        "int8_t":    "i8",
        "int16_t":   "i16",
        "int32_t":   "i32",
        "int64_t":   "i64",
        "uint8_t":   "u8",
        "uint16_t":  "u16",
        "uint32_t":  "u32",
        "uint64_t":  "u64",
        "size_t":    "uptr",
        "ptrdiff_t": "iptr",
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

    # remap chains of aliases
    for alias in typeNameRemap:
        prevAlias = None
        newAlias = alias
        while newAlias != prevAlias:
            prevAlias = newAlias
            if prevAlias in typeNameRemap:
                newAlias = typeNameRemap[prevAlias]

        typeNameRemap[alias] = newAlias

    for alias in typealiases.values():
        parseAlias(alias, typeNameRemap)
        objects[alias.name] = alias

    for alias in typedefs.values():
        parseAlias(alias, typeNameRemap)
        objects[alias.name] = alias

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
        parseCommand(command, typeNameRemap, commands)
        objects[command.name] = command

    for feature in list(features.values()):
        parseFeature(feature, typeNameRemap, enums)

    for extension in list(extensions.values()):
        parseExtenstion(extension, typeNameRemap, enums, structures, commands, objects)

    for object in objects.values():
        object.inferPlatform()

    for platform in supportedPlatforms:
        genOpts = GenOpts(api="vulkan", platform=platform, nameFilter=["video"])
        generateDefsForPlatform(genOpts, typealiases, typedefs, constants, structures, enums, funcPtrs, commands, extensions, objects)

    print("Generated vulkan module successfully!\nTotals:")
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
