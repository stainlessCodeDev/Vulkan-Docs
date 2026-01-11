include "VulkanWindows.nl"

import "Lib"

func VK_MAKE_API_VERSION(u32 variant, u32 major, u32 minor, u32 patch) => u32
{
    return (variant << 29) | (major << 22) | (minor << 12) | (patch);
}

func VK_API_VERSION_VARIANT(u32 version) => u32
{
    return version >> 29;
}

func VK_API_VERSION_MAJOR(u32 version) => u32
{
    return (version >> 22) & 0x7F;
}

func VK_API_VERSION_MINOR(u32 version) => u32
{
    return (version >> 12) & 0x3FF;
}

func VK_API_VERSION_PATCH(u32 version) => u32
{
    return version & 0xFFF;
}

const VK_API_VERSION_1_0 = VK_MAKE_API_VERSION(0, 1, 0, 0);
const VK_API_VERSION_1_1 = VK_MAKE_API_VERSION(0, 1, 1, 0);
const VK_API_VERSION_1_2 = VK_MAKE_API_VERSION(0, 1, 2, 0);
const VK_API_VERSION_1_3 = VK_MAKE_API_VERSION(0, 1, 3, 0);
const VK_API_VERSION_1_4 = VK_MAKE_API_VERSION(0, 1, 4, 0);

callback VulkanAPIStub() => void
{
    // This should like trigger a breakpoint or crash, but will allow us to get a proper callstack
    Assert(false, "Called VulkanAPIStub, some api wasn't loaded properly!");
}
