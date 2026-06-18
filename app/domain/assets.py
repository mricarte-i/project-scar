from enum import StrEnum


class AssetType(StrEnum):
    DARKFRAME = "darkframe"
    GRAYFRAME = "grayframe"
    VICARIOUS_CAL_GAINS = "vicarious_cal_gains"
    BODY_TO_PAYLOAD = "body_to_payload"


def is_frame(asset_type: AssetType) -> bool:
    return asset_type in [AssetType.DARKFRAME, AssetType.GRAYFRAME]


class MediaType(StrEnum):
    FRAME_MEDIA_TYPE = "application/x-npy"
    JSON_MEDIA_TYPE = "application/json"


def media_type_for(asset_type: AssetType) -> MediaType:
    return (
        MediaType.FRAME_MEDIA_TYPE
        if is_frame(asset_type)
        else MediaType.JSON_MEDIA_TYPE
    )
