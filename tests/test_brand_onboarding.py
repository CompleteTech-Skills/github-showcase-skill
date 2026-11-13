"""Synthetic local brand onboarding, including refusal and no-write controls."""
import argparse
import json

import pytest
from PIL import Image

from ctshowcase.brand_commands import cmd_brand, register
from ctshowcase.color import contrast
from ctshowcase.config import Brand, load_yaml_text, schema_errors
from ctshowcase.errors import ConfigError, Refused


def args_for(path, *argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    register(parser.add_subparsers(dest='command'))
    return parser.parse_args(['--config', str(path), 'brand', *argv])


@pytest.fixture
def local_config(tmp_path, brand):
    path = tmp_path / 'references' / 'brand.yaml'
    path.parent.mkdir()
    path.write_text(brand.path.read_text(encoding='utf-8'), encoding='utf-8')
    return path


def family_args(path, *extra):
    return args_for(path, 'add-family', '--name', 'northwind-new', '--label', 'Northwind New',
                    '--canvas', '#101820', '--ink', '#F5F5F5', '--accent', '#FFB81C', *extra)


def test_one_command_adds_isolated_family_org_mark_and_lock(local_config):
    mark = local_config.parent.parent / 'input.png'
    Image.new('RGBA', (16, 16), (20, 30, 40, 255)).save(mark)
    before = local_config.read_text(encoding='utf-8')
    args = family_args(local_config, '--org', 'Northwind-New', '--display-name', 'Northwind New',
                       '--tier', 'T2', '--footer', 'no', '--mark', str(mark))
    result, code = cmd_brand(args)
    assert code == 0 and result['result'] == 'planned'
    assert local_config.read_text(encoding='utf-8') == before
    assert not (local_config.parent.parent / 'assets').exists()
    args.write = True
    result, code = cmd_brand(args)
    raw = load_yaml_text(local_config.read_text(encoding='utf-8'))
    assert raw == json.loads(local_config.with_name('brand.lock.json').read_text(encoding='utf-8'))
    assert not schema_errors(raw)
    assert '# CompleteTech showcase brand config:' in local_config.read_text(encoding='utf-8')
    assert raw['orgs']['Northwind-New']['footer'] is False
    assert raw['orgs']['Northwind-New']['family'] == 'northwind-new'
    assert (local_config.parent.parent / 'assets/orgs/Northwind-New/mark.png').read_bytes() == mark.read_bytes()
    style = Brand(raw, local_config).style('Northwind-New')
    assert style['company_label'] == 'Northwind New'
    for key in ('eyebrow', 'title', 'subtitle', 'body', 'icon_ink', 'icon_spark'):
        assert contrast(style['tokens'][key], style['canvas']['color']) >= 4.5
    for key in ('chip_key', 'chip_attr'):
        assert contrast(style['tokens'][key]['bg'], style['tokens'][key]['fg']) >= 4.5
    assert style['measured'] is False


def test_add_org_requires_explicit_policy_and_preserves_t3_refusal(local_config):
    args = args_for(local_config, 'add-org', '--family', 'pickyourai', '--org', 'Northwind-Team',
                    '--display-name', 'Northwind Team')
    before = local_config.read_bytes()
    with pytest.raises(ConfigError, match='--tier and --footer'):
        cmd_brand(args)
    assert local_config.read_bytes() == before
    args.tier, args.footer, args.write = 'T3', 'hold', True
    cmd_brand(args)
    raw = load_yaml_text(local_config.read_text(encoding='utf-8'))
    b = Brand(raw, local_config)
    with pytest.raises(Refused):
        b.check_owner('northwind-team')
    assert raw['orgs']['Northwind-Team']['footer'] == 'hold'


@pytest.mark.parametrize('option,value,match', [
    ('canvas', '#F5F5F5', 'must be dark'),
    ('ink', '#101820', 'contrast'),
    ('accent', 'red', 'six-digit'),
    ('icon_ink', '#101820', 'contrast'),
    ('label', 'Northwind\nForged', 'single line'),
])
def test_invalid_palette_writes_nothing(local_config, option, value, match):
    args = family_args(local_config, '--write')
    setattr(args, option, value)
    before = local_config.read_bytes()
    with pytest.raises(ConfigError, match=match):
        cmd_brand(args)
    assert local_config.read_bytes() == before
    assert not local_config.with_name('brand.lock.json').exists()


@pytest.mark.parametrize('name', ['CompleteTech-Skills', 'completetech-skills', 'CompleTetech-Security', 'BunsDev'])
def test_reserved_or_aliased_org_cannot_be_reclassified(local_config, name):
    args = family_args(local_config, '--org', name, '--display-name', 'Northwind New',
                       '--tier', 'T1', '--footer', 'yes', '--write')
    before = local_config.read_bytes()
    with pytest.raises(ConfigError, match='exists or is reserved'):
        cmd_brand(args)
    assert local_config.read_bytes() == before


def test_failed_mark_validation_does_not_add_family(local_config):
    mark = local_config.parent.parent / 'input.png'
    mark.write_bytes(b'not an image')
    args = family_args(local_config, '--org', 'Northwind-New', '--display-name', 'Northwind New',
                       '--tier', 'T2', '--footer', 'no', '--mark', str(mark), '--write')
    before = local_config.read_bytes()
    with pytest.raises(ConfigError, match='valid PNG'):
        cmd_brand(args)
    assert local_config.read_bytes() == before


def test_schema_failure_writes_nothing(local_config, monkeypatch):
    import ctshowcase.brand_commands as module
    monkeypatch.setattr(module, 'schema_errors', lambda _: ['synthetic failure'])
    before = local_config.read_bytes()
    with pytest.raises(ConfigError, match='synthetic failure'):
        cmd_brand(family_args(local_config, '--write'))
    assert local_config.read_bytes() == before


def test_existing_family_never_replaced(local_config):
    args = family_args(local_config, '--write')
    args.name = 'completetech'
    before = local_config.read_bytes()
    with pytest.raises(ConfigError, match='already exists'):
        cmd_brand(args)
    assert local_config.read_bytes() == before
