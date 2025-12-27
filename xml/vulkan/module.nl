include "VulkanDefs.nl"

import "Windows"

proc LoadVulkan() => bool
{
    HMODULE vulkan = LoadLibraryA("vulkan-1.dll");

    if (vulkan == null)
        return false;
    
    vkGetInstanceProcAddr = GetProcAddress(vulkan, "vkGetInstanceProcAddr");

    if (vkGetInstanceProcAddr == null)
        return false;
    
    return true;
}

proc InitVulkan() => bool
{
    return true;
}

callback VulkanAPIStub() => void
{
    // This should like trigger a breakpoint or crash, but will allow us to get a proper callstack
    Assert(false);
}
