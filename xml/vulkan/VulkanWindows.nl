include "VulkanCore.nl"
include "VulkanWin32.nl"

import "Lib"
import "Windows"

proc LoadVulkan() => bool
{
    HMODULE vulkan = LoadLibrary("vulkan-1.dll");

    if (vulkan == null)
        return false;
    
    vkGetInstanceProcAddr = GetProcAddress(vulkan, "vkGetInstanceProcAddr");

    if (vkGetInstanceProcAddr == null)
        return false;
    
    return true;
}