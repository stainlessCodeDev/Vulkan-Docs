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
    supportedPlatforms: list[str] = field(default_factory=list[str])
    nameFilter: list[str] = field(default_factory=list[str])
    vendorFilter: list[str] = field(default_factory=list[str])

    def ignoreNameFilter(self):
        return GenOpts(api=self.api, platform=self.platform, supportedPlatforms=self.supportedPlatforms, nameFilter=[])

    def ignorePlatform(self):
        return GenOpts(api=self.api, platform=None, supportedPlatforms=self.supportedPlatforms, nameFilter=self.nameFilter)

@dataclass
class BaseObject:
    name: str = field(default="", init=False)
    type: str = field(default=None, init=False)
    node: etree.Element = field(default=None, init=False)

    platform: str = field(default="Core", init=False)
    #enabledCounter: int = field(default=0, init=False)
    apis: list[str] = field(default_factory=list[str], init=False)
    users: list[BaseObject] = field(default_factory=list[str], init=False)

    def setPlatform(self, platform):
        self.platform = platform

        for child in self:
            child.setPlatform(platform)

    def inferPlatform(self):
        if self.platform == "Core":
            for child in self:
                child.inferPlatform()
                if child.platform != "Core":
                    self.platform = child.platform

    def isDisabled(self, genOpts = None):
        if self.isDisabledImpl(genOpts):
            return True
        elif not isinstance(self, Extension) and not isinstance(self, Feature) and all([user.isDisabled(genOpts) for user in self.users]):
            return True
        elif genOpts == None:
            return False
        elif genOpts.api != None and len(self.apis) > 0 and genOpts.api not in self.apis:
            return True
        elif genOpts.platform != None and self.platform != genOpts.platform:
            return True
        elif genOpts.platform == None and self.platform not in genOpts.supportedPlatforms:
            return True
        else:
            for filter in genOpts.nameFilter:
                if filter.casefold() in self.name.casefold():
                    return True
        return False

    def isDisabledImpl(self, genOpts):
        return False

    #def setDisabled(self, disable):
    #    if disable:
    #        self.enabledCounter -= 1
    #    else:
    #        self.enabledCounter += 1

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

isNumber = re.compile("\\(?(~?\\d+\\.?\\d*)[FfUuLl]*\\)?", re.VERBOSE)

@dataclass
class EnumMember(BaseObject):
    value: str = field(default=None, init=False)
    isConst: bool = field(default=False, init=False)

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        value = isNumber.match(self.value)
        if value:
            value = value.groups()[0]
        else:
            value = self.value

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
        if self.isDisabled(genOpts.ignoreNameFilter()):
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

    def toDefn(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if self.name == "":
            return ""

        return self.name

@dataclass
class Command(BaseObject):
    args: list[CommandArgument] = field(default_factory=list[CommandArgument], init=False)
    alias: str = field(default=None, init=False)
    export: list[str] = field(default_factory=list[str], init=False)
    category: str = field(default="instance", init=False)

    def __iter__(self):
        for arg in self.args:
            yield arg

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if self.alias != None:
            return ""

        argsDecl = ", ".join(a for a in [arg.toDecl(genOpts) for arg in self] if a)
        argsDefn = ", ".join(a for a in [arg.toDefn(genOpts) for arg in self] if a)

        # genOpts.api != None and genOpts.api in self.export

        if self.category in ["instance", "physicalDevice", "instance_extension"]:
            # these are directly exported from vulkan-1.dll, so we import them via linking, we should trim the vk off of the name [2:]
            return f"global ({argsDecl}) => {self.type} {self.name} = cast(void*)&VulkanAPIStub;\n"
        elif False:
            return f"""global ({argsDecl}) => {self.type} {self.name} = &{self.name}Stub;\n
@Private
callback {self.name}Stub({argsDecl}) => {self.type}\n{{
    {self.name} = vkGetInstanceProcAddr(instance, "{self.name}");
    if ({self.name} == null)\n    {{
        Assert(false, "Vulkan not loaded!\\n");
        {self.name} = cast(void*)&{self.name}Stub;
        return{f" cast({self.type})0" if self.type != "void" else ""};
    }}

    return {self.name}({argsDefn});
}}\n\n"""
        else:
            return ""

    def toDeviceTableMember(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if self.alias != None:
            return ""

        argsDecl = ", ".join(a for a in [arg.toDecl(genOpts) for arg in self] if a)
        argsDefn = ", ".join(a for a in [arg.toDefn(genOpts) for arg in self] if a)

        if self.category not in ["instance", "physicalDevice", "instance_extension"]:
            return "    ({}) => {} {};\n".format(argsDecl, self.type, self.name)
        else:
            return ""

    def toDeviceTableLoad(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if self.alias != None:
            return ""

        if self.category not in ["instance", "physicalDevice", "instance_extension", "device_extension"]:
            return f"    table.{self.name} = cast(void*) vkGetDeviceProcAddr(device, \"{self.name}\");\n"
        else:
            return ""

@dataclass
class Feature(BaseObject):
    pass

@dataclass
class Extension(BaseObject):
    kind: str = field(default=None, init=False)
    number: int = field(default=None, init=False)
    commandsToLoad: list[Command] = field(default_factory=list[Command], init=False)
    vendor: str = field(default=None, init=False)

    def toDecl(self, genOpts):
        if self.isDisabled(genOpts):
            return ""

        if len(self.commandsToLoad) == 0:
            return ""

        args = "VkDevice device, VkDevicePtrTable* table"
        load = "table.{} = cast(void*) vkGetDeviceProcAddr(device, \"{}\");"
        if self.kind == "instance":
            args = "VkInstance instance"
            load = "{} = cast(void*) vkGetInstanceProcAddr(instance, \"{}\");"

        result = f"""proc Load{self.name}({args}) => bool
{{
"""
        # maybe even we can do a check for extension existance or something,
        # need to learn a bit more about extensions and if there anything special needs to be done to load one

        commandCounter = 0
        for commandToLoad in self.commandsToLoad:
            command = commandToLoad

            if command.alias != None:
                command = command.alias
                result += f"    //{load.format(command.name, commandToLoad.name)} //aliased\n"
                continue

            result += f"    {load.format(command.name, commandToLoad.name)}\n"
            commandCounter += 1

        if commandCounter == 0:
            return ""

        return result + "    return true;\n}\n\n"

    def isDisabledImpl(self, genOpts):
        if "disabled" in self.apis:
            return True
        elif self.vendor and len(genOpts.vendorFilter) > 0 and self.vendor not in genOpts.vendorFilter:
            return True
        return False

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

        if "author" in extensionNode.attrib:
            extension.vendor = extensionNode.attrib["author"]

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
        member.users.append(structure)

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
                argument.users.append(funcPtr)

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

        enum.name = typeNameRemap[enum.name]
        enums[enum.name] = enum

        if enum.name in typedefs:
            alias = typedefs[enum.name]
            typedefs.pop(enum.name)
            enum.type = typeNameRemap[alias.type]
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
            enumValue.users.append(enum)

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
            arg.users.append(command)
        else:
            continue

    if len(command.args) > 0 and command.args[0].name in ["instance", "physicalDevice", "device", "queue", "commandBuffer"]:
        command.category = command.args[0].name

    if "export" in command.node.attrib:
        command.export = command.node.attrib["export"].split(",")

def parseEnumExtension(itemNode, extendsEnum, name, typeNameRemap, constants, extNumber):

    enumValue = EnumMember()
    enumValue.name = name

    if "bitpos" in itemNode.attrib:
        enumValue.value = "1 << {}".format(itemNode.attrib["bitpos"])
    elif "value" in itemNode.attrib:
        enumValue.value = itemNode.attrib["value"]
    elif "alias" in itemNode.attrib:
        enumValue.value = itemNode.attrib["alias"]
    elif "extnumber" in itemNode.attrib:
        extNumber = int(itemNode.attrib["extnumber"]) # Why is it -1???
        enumValue.value = str((1000000 + extNumber - 1) * 1000 + int(itemNode.attrib["offset"]))
    elif "offset" in itemNode.attrib and extNumber:
        enumValue.value = str((1000000 + extNumber - 1) * 1000 + int(itemNode.attrib["offset"]))
    else:
        return constants[name]

    if extendsEnum:
        extendsEnum.members[name] = enumValue
    else:
        enumValue.isConst = True
        constants[name] = enumValue

    return enumValue

def parseFeature(feature, typeNameRemap, objects, enums, constants):
    for requireNode in feature.node:
        if requireNode.tag != "require":
            continue

        for itemNode in requireNode:
            name = None
            if "name" in itemNode.attrib:
                name = itemNode.attrib["name"] # enum name trimming

            if itemNode.tag == "enum":
                extendsEnum = None

                if "extends" in itemNode.attrib:
                    extendsEnum = enums[typeNameRemap[itemNode.attrib["extends"]]]

                value = parseEnumExtension(itemNode, extendsEnum, name, typeNameRemap, constants, None)
                value.users.append(feature)
            elif itemNode.tag == "type" and name in typeNameRemap:
                object = objects[typeNameRemap[name]]
                object.users.append(feature)
            elif itemNode.tag == "command":
                object = objects[name]
                object.users.append(feature)

def parseExtenstion(extension, typeNameRemap, enums, structures, commands, constants, objects):
    for requireNode in extension.node:
        if requireNode.tag != "require":
            continue

        for itemNode in requireNode:
            name = None
            if "name" in itemNode.attrib:
                name = itemNode.attrib["name"] # enum name trimming

            if itemNode.tag == "enum":
                extendsEnum = None
                if "extends" in itemNode.attrib:
                    extendsEnum = enums[typeNameRemap[itemNode.attrib["extends"]]]

                value = parseEnumExtension(itemNode, extendsEnum, name, typeNameRemap, constants, extension.number)
                value.setPlatform(extension.platform)
                #value.setDisabled(extension.isDisabled())
                value.users.append(extension)
            elif itemNode.tag == "command":
                command = commands[name]
                extension.commandsToLoad.append(command)
                if extension.kind == "instance":
                    command.category = "instance_extension"
                else:
                    command.category = "device_extension"
                command.setPlatform(extension.platform)
                #command.setDisabled(extension.isDisabled())
                command.users.append(extension)
            elif itemNode.tag == "type":
                type = objects[typeNameRemap[name]]
                type.setPlatform(extension.platform)
                #type.setDisabled(extension.isDisabled())
                type.users.append(extension)

def generateDefsForPlatform(genOpts, typealiases, typedefs, constants, structures, enums, funcPtrs, commands, extensions, objects):
    filePlatform = genOpts.platform.capitalize()

    with open("vulkan/Vulkan{}.nl".format(filePlatform), "w") as f:
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

        f.write(f"\nstruct VkDevicePtrTable{filePlatform}\n{{\n")

        for command in commands.values():
            f.write(command.toDeviceTableMember(genOpts))

        f.write("}\n")

        f.write(f"\nproc vkLoadDevicePtrTable{filePlatform}(VkDevice device, DevicePtrTable* table) => void\n{{\n")

        for command in commands.values():
            f.write(command.toDeviceTableLoad(genOpts))
        f.write("}\n\n")

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
        parseFeature(feature, typeNameRemap, objects, enums, constants)

    for extension in list(extensions.values()):
        parseExtenstion(extension, typeNameRemap, enums, structures, commands, constants, objects)

    for object in objects.values():
        object.inferPlatform()

    for platform in supportedPlatforms:
        genOpts = GenOpts(api="vulkan", platform=platform, supportedPlatforms=supportedPlatforms, nameFilter=["video", "_SPEC_VERSION"], vendorFilter=["KHR", "EXT"])
        generateDefsForPlatform(genOpts, typealiases, typedefs, constants, structures, enums, funcPtrs, commands, extensions, objects)

    print("Generated vulkan module successfully!")

if __name__ == '__main__':
    main()
