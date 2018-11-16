#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2018, University of California, Berkeley
# author: Kevin Laeufer <laeufer@cs.berkeley.edu>

import re, os, datetime, sys

########################################################################################################################
# very hacky, rudimentary, vim syntax parsing

def flat_map(itr, fun):
	items = (fun(ii) for ii in itr)
	return (ii for ii in items if ii is not None)

meta_data_re = re.compile(r'^" (Language|Maintainer|Filenames): (.+)$')
syn_cmd_re = re.compile(r'^syn (keyword|match|region)\s+(\w+)\s+(.+)$')
hi_def_link_re = re.compile(r'^hi def link (\w+)\s+(\w+)$')
options_re = re.compile(r'^(display)\s+(.+)$')
match_re = re.compile(r'^start="([^"]+)"\s+end="([^"]+)"$')

def parse_vim_syn(cmd, args):
	options = []
	if cmd == "keyword":
		return [a.strip() for a in args.split(' ')], options
	m = options_re.match(args)
	if m is not None:
		options = [m.group(1).strip()]
		args = m.group(2).strip()
	if cmd == "match":
		assert args.startswith('"'), f"{args[0]} {args}"
		assert args.endswith('"'), f"{args[-1]} {args}"
		args = args[1:-1]
		return [args], options
	if cmd == "region":
		m = match_re.match(args)
		assert m is not None
		return [m.group(1), m.group(2)], options
	raise NotImplementedError(f"unknown syn command {cmd}")

def parse_vim_line(line):
	m = meta_data_re.match(line)
	if m is not None:
		return {'name': m.group(1).lower(), 'value': m.group(2).strip()}
	m = syn_cmd_re.match(line)
	if m is not None:
		cmd, ii, args = m.group(1,2,3)
		args, options = parse_vim_syn(cmd, args)
		return {'name': cmd, 'id': ii, 'args': args, 'options': options}
	m = hi_def_link_re.match(line)
	if m is not None:
		return {'name': 'link', 'id': m.group(1), 'style': m.group(2)}

def parse_vim(lines):
	meta_names = {'language', 'maintainer', 'filenames'}
	declarations = list(flat_map(lines, parse_vim_line))
	meta = {ii['name']: ii['value'] for ii in declarations if ii['name'] in meta_names}
	other = [ii for ii in declarations if ii['name'] not in meta_names]
	return meta, other

class StyleVisitor:
	def visit(self, meta, declarations):
		# self.visit_meta(language=meta.get('language', ''),
		# 				maintainer=meta.get('maintainer', ''),
		# 				filenames=meta.get('filenames', ''))
		for d in declarations:
			name = d['name']
			if name == 'keyword':
				self.visit_keyword(ii=d['id'], words=d['args'])
			elif name == 'match':
				self.visit_match(ii=d['id'], regex=d['args'][0])
			elif name == 'region':
				self.visit_region(ii=d['id'], start=d['args'][0], end=d['args'][1])
			elif name == 'link':
				self.visit_link(ii=d['id'], style=d['style'])

########################################################################################################################
# GTK Source Emitter
# https://developer.gnome.org/gtksourceview/stable/lang-tutorial.html
########################################################################################################################
GTKSourceViewHeader = """
<!--

 This file is part of GtkSourceView

 Authors: {authors}
 Copyright (C) {year} {authors}

 GtkSourceView is free software; you can redistribute it and/or
 modify it under the terms of the GNU Lesser General Public
 License as published by the Free Software Foundation; either
 version 2.1 of the License, or (at your option) any later version.

 GtkSourceView is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 Lesser General Public License for more details.

 You should have received a copy of the GNU Lesser General Public
 License along with this library; if not, write to the Free Software
 Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

-->
"""

GeneratorHeader = "<!-- Automatically generated from {src} using {tool}. Do not edit! -->"

MetaData = """
  <metadata>
    <property name="globs">{globs}</property>
    <property name="mimetypes">text/plain</property>
    <property name="line-comment-start">{line}</property>
    <property name="block-comment-start">{block_start}</property>
    <property name="block-comment-end">{block_end}</property>
  </metadata>"""

Styles = {
	'comment': 'comment',
	'Identifier': 'type',
	'Type': 'type',
	'Keyword': 'keyword',
	'Conditional': 'keyword',
	'StorageClass': 'keyword',
	'Constant': 'constant',
	'Define': 'preprocessor',
	'Special': 'special-constant',
	'Number': 'decimal',

}

SkipDecls = {'ucl4Identifier'}

def regex_vim_to_gtk_src(regex):
	regex = regex.replace('\\<', '')
	regex = regex.replace('\\>', '')
	regex = regex.replace('\\+', '+')
	return regex


class GtkSourceEmitter(StyleVisitor):
	def __init__(self, out, declarations, meta):
		self.out = out
		self.declarations = [dd for dd in declarations if dd['name'] != 'link' and dd['id'] not in SkipDecls]
		self.meta = meta
		links = [dd for dd in declarations if dd['name'] == 'link']
		self.id_to_style = { ll['id']: ll['style'] for ll in links }
		self.contexts = []

	def get_syn(self, ii):
		for dd in self.declarations:
			if dd['name'] != 'link' and dd.get('id', '') == ii:
				return dd
		raise RuntimeError(f"declaration with id {ii} not found!")

	def get_style(self, ii):
		style = self.id_to_style[ii]
		if style in self.id_to_style:
			return self.get_style(style)
		assert style in Styles
		return style

	def print(self, string=''):
		print(string, file=self.out)

	def print_header(self, filename, author, lang):
		self.print('<?xml version="1.0" encoding="UTF-8"?>')
		authors = f"Kevin Läufer <laeufer@eecs.berkeley.edu> and {author}"
		year = str(datetime.datetime.now().year)
		self.print(GTKSourceViewHeader.format(authors=authors, year=year))
		tool = os.path.basename(__file__)
		self.print(GeneratorHeader.format(tool=tool, src=os.path.basename(filename)))
		self.print()
		Lang = lang[0].upper() + lang[1:]
		self.print('<language id="{lang}" _name="{Lang}" version="2.0" _section="Source">'.format(lang=lang, Lang=Lang))

	def print_metadata(self, glob):
		multi_start, multi_end = self.get_syn('ucl4MultilineComment')['args']
		line_start = self.get_syn('ucl4TrailingComment')['args'][0]
		self.print(MetaData.format(globs=glob, line=line_start, block_start=multi_start.replace('\\',''),
								   block_end=multi_end.replace('\\','')))

	def print_styles(self):
		self.print('  <styles>')
		for ii, map_to in Styles.items():
			self.print('    <style id="{ii}" name="{ii}" map-to="def:{map_to}"/>'.format(ii=ii, map_to=map_to))
		self.print('  </styles>')

	def start_context(self, ii):
		style = self.get_style(ii)
		self.print()
		self.print('    <context id="{ii}" style-ref="{style}">'.format(ii=ii, style=style))
		self.contexts.append(ii)

	def end_context(self):
		self.print('    </context>')

	def visit_keyword(self, ii, words):
		self.start_context(ii)
		for word in words:
			self.print('      <keyword>{}</keyword>'.format(word))
		self.end_context()

	def visit_match(self, ii, regex):
		print(f"{regex} --> {regex_vim_to_gtk_src(regex)}")
		regex = regex_vim_to_gtk_src(regex)
		if '<' in regex:
			return
		self.start_context(ii)
		self.print('      <match extended="true">')
		self.print('        ' + regex)
		self.print('      </match>')
		self.end_context()

	def visit_region(self, ii, start, end):
		start = start.replace('/', '\\/')
		end = end.replace('/', '\\/')
		self.start_context(ii)
		self.print(f'      <start>{start}</start>')
		self.print(f'      <end>{end}</end>')
		self.end_context()

	def run(self, filename):
		self.contexts = []
		lang = self.meta['language']
		self.print_header(filename, self.meta['maintainer'], lang)
		self.print_metadata(self.meta['filenames'])
		self.print_styles()

		self.print()
		self.print('  <definitions>')
		self.visit(self.meta, self.declarations)

		# main language context
		self.print(f'    <context id="{lang}">')
		self.print('      <include>')
		for ctx in self.contexts:
			self.print(f'        <context ref="{ctx}" />')
		self.print('      </include>')
		self.end_context()

		self.print('  </definitions>')
		self.print('</language>')



if __name__ == '__main__':
	cwd = os.path.dirname(os.path.abspath(__file__))
	vim_file_name = os.path.join(cwd, 'uclid.vim')
	with open(vim_file_name) as ff:
		style_meta, style_declaration = parse_vim(ff)
	for d in style_declaration:
		print(f"{d['name']}: {d}")

	with open('uclid.lang.gen', 'w') as out:
		emitter = GtkSourceEmitter(out, style_declaration, meta=style_meta)
		emitter.run(vim_file_name)