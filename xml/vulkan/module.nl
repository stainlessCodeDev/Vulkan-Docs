include "VulkanWindows.nl"

proc InitVulkan() => bool
{
    return true;
}

callback VulkanAPIStub() => void
{
    // This should like trigger a breakpoint or crash, but will allow us to get a proper callstack
    Assert(false);
}
