import os
import re
import xml.etree.ElementTree as etree
from types import SimpleNamespace

def iterMixed(elem):
    if elem.text:
        yield elem.text

    for child in elem:
        yield child
        if child.tail:
            yield child.tail

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

        

def fetchFeatures(featuresNode, typeNameRemap, features):
    pass

def parseStruct(structure, typeNameRemap):
    #print("\nstruct {}".format(structure.name))
    for memberNode in structure.node:
        if memberNode.tag != "member":
            continue
        if memberNode.attrib.get("api") != None:
            if "vulkan" not in memberNode.attrib["api"].split(","):
                continue
        
        member = SimpleNamespace()
        member.name = ""
        member.type = ""
        for node in iterMixed(memberNode):
            if isinstance(node, str):
                node = node.strip()
                if node != "const":
                    member.type = " ".join([member.type, node]).strip()
                continue
            if node.tag == "type":
                member.type = " ".join([member.type, typeNameRemap[node.text.strip()]["name"]]).strip()
                continue
            if node.tag == "enum":
                member.type = " ".join([member.type, node.text.strip()]).strip()
                continue
            if node.tag == "name":
                member.name = node.text

        #print("  {}".format(member))
        structure.members.append(member)

def parseFuncPtr(funcPtr, typeNameRemap):
    pass

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

def parseCommand(command, typeNameRemap):
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