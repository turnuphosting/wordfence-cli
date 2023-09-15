import re
from typing import List, Dict, Union, Optional, Callable, Any


PHP_VERSION_DELIMITER = '.'
PHP_VERSION_ALTERNATE_DELIMITERS = ['_', '-', '+']


NON_NUMBER_PATTERN = re.compile('[^0-9.]+')
NUMBER_PATTERN = re.compile('^[0-9]+$')
REPEATED_DOT_PATTERN = re.compile('\\.{2,}')


def delimit_non_numbers(version: str) -> str:
    return NON_NUMBER_PATTERN.sub(".\\g<0>.", version).strip('.')


def is_number(string: str) -> bool:
    return NUMBER_PATTERN.match(string) is not None


def strip_repeated_delimiters(version: str) -> str:
    return REPEATED_DOT_PATTERN.sub('.', version)


LOWER_ALPHA_VERSIONS = [
    ['dev'],
    ['alpha', 'a'],
    ['beta', 'b'],
    ['RC', 'rc'],
]
HIGHER_ALPHA_VERSIONS = [
    ['pl', 'p']
]
TIER_OFFSET = 2
TIER_NUMBER = len(LOWER_ALPHA_VERSIONS) + TIER_OFFSET


def create_alpha_version_map(versions: List[List[str]]) -> Dict[str, int]:
    map = {}
    for index, tier in enumerate(versions):
        for version in tier:
            map[version] = index
    return map


LOWER_ALPHA_VERSION_MAP = create_alpha_version_map(LOWER_ALPHA_VERSIONS)
HIGHER_ALPHA_VERSIONS_MAP = create_alpha_version_map(HIGHER_ALPHA_VERSIONS)


def get_alpha_tier(string: str, map: Dict[str, int]) -> Optional[int]:
    try:
        return map[string]
    except KeyError:
        return None


def get_lower_alpha_tier(string: str) -> Optional[int]:
    return get_alpha_tier(string, LOWER_ALPHA_VERSION_MAP)


def get_higher_alpha_tier(string: str) -> Optional[int]:
    return get_alpha_tier(string, HIGHER_ALPHA_VERSIONS_MAP)


class PhpVersionComponent:

    def __init__(self, value: str):
        self.is_number = is_number(value)
        if self.is_number:
            self.value = int(value)
        else:
            self.value = value
        self.lower_alpha_tier = \
            None if self.is_number else get_lower_alpha_tier(self.value)
        self.higher_alpha_tier = \
            None if self.is_number else get_higher_alpha_tier(self.value)
        self.tier = self._evaluate_tier()

    def _evaluate_tier(self) -> int:
        if self.lower_alpha_tier is not None:
            return self.lower_alpha_tier + TIER_OFFSET
        if self.is_number:
            return TIER_NUMBER
        if self.higher_alpha_tier is not None:
            return TIER_NUMBER + 1 + self.higher_alpha_tier
        if not self.is_number and self.lower_alpha_tier is None \
                and self.higher_alpha_tier is None:
            return 1
        return 0

    def __str__(self) -> str:
        return str(self.value)


DefaultComponent = PhpVersionComponent('0')


class PhpVersion:

    def __init__(self, version: str):
        self.version = version
        self._components = self.extract_components(version)

    def extract_components(self, version: str) -> List[str]:
        for character in PHP_VERSION_ALTERNATE_DELIMITERS:
            version = version.replace(character, PHP_VERSION_DELIMITER)
        # Note that this also strips leading/trailing delimiters
        version = strip_repeated_delimiters(
                delimit_non_numbers(version)
            )
        return list(map(PhpVersionComponent, version.split('.')))

    def _get_component(self, index: int) -> PhpVersionComponent:
        try:
            return self._components[index]
        except IndexError:
            return DefaultComponent


def compare_version_components(
            a: Optional[PhpVersionComponent],
            b: Optional[PhpVersionComponent]
        ) -> int:
    print(vars(a))
    print(vars(b))
    if a.value == b.value:
        return 0
    if a.tier != b.tier:
        return -1 if a.tier < b.tier else 1
    if a.tier == 0 or a.tier == TIER_NUMBER:
        return -1 if a.value < b.value else 1
    return 0


def compare_php_versions(
            a: Union[PhpVersion, str],
            b: Union[PhpVersion, str]
        ) -> int:
    """ This is intended to mirror PHP's version_compare function  """
    """ https://www.php.net/manual/en/function.version-compare.php """
    if not isinstance(a, PhpVersion):
        a = PhpVersion(a)
    if not isinstance(b, PhpVersion):
        b = PhpVersion(b)
    component_count = max(len(a._components), len(b._components))
    for i in range(0, component_count):
        comparison = compare_version_components(
                a._get_component(i),
                b._get_component(i)
            )
        if comparison != 0:
            return comparison
    return 0
