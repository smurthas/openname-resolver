#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
	Openname-resolver
	~~~~~

	:copyright: (c) 2014 by Openname.org
	:license: MIT, see LICENSE for more details.
"""

from flask import Flask, make_response, jsonify, abort, request
import json 

from commontools import error_reply

app = Flask(__name__)

from .config import DEFAULT_HOST, MEMCACHED_SERVERS, MEMCACHED_USERNAME, MEMCACHED_PASSWORD, MEMCACHED_TIMEOUT, MEMCACHED_ENABLED
import pylibmc
from time import time
mc = pylibmc.Client(MEMCACHED_SERVERS,binary=True,username=MEMCACHED_USERNAME,password=MEMCACHED_PASSWORD)

from coinrpc import namecoind 

from .helper import requires_auth

#-----------------------------------
def name_show_mem(key):

	if MEMCACHED_ENABLED: 
		cache_reply = mc.get("name_" + str(key))
	else:
		cache_reply = None
  
	if cache_reply is None:
		try: 
			info = namecoind.name_show(key)
		

			if MEMCACHED_ENABLED:
				mc.set("name_" + str(key),json.dumps(info['value']),int(time() + MEMCACHED_TIMEOUT))
				#print "cache miss: " + str(key)
		except:
			info = {}
	else:
		#print "cache hit: " + str(key)
		info = {}
		info['value'] = json.loads(cache_reply)

	return info

#-----------------------------------
def full_profile_mem(key):

	check_profile = name_show_mem(key)
	
	try:
		check_profile = check_profile['value']
	except:
		return check_profile
				
	if 'next' in check_profile:
		try:
			child_data = name_show_mem(check_profile['next'])
			child_data = child_data['value']
		except:
			return check_profile

		del check_profile['next']

		merged_data = {key: value for (key, value) in (check_profile.items() + child_data.items())}
		return merged_data

	else:
		return check_profile

#-----------------------------------
@app.route('/resolver/value')
@requires_auth
def get_key_value():

	try:
		key = request.args.get('key').lower()
	except:
		return jsonify(error_reply("No key given"))

	info = name_show_mem(key)

	if 'status' in info:
		if info['status'] == 404:
			abort(404)
			
	return jsonify(info)


#-----------------------------------
@app.route('/resolver/profile')
@requires_auth
def get_openname_profile():
	
	try:
		key = 'u/' + request.args.get('openname').lower()
	except:
		return jsonify(error_reply("No openname given"))
	
	if MEMCACHED_ENABLED: 
		cache_reply = mc.get("profile_" + str(key))
	else:
		cache_reply = None
		#print "cache off"

	if cache_reply is None: 

		try:
			info = full_profile_mem(key)
			jsonify(info)
		except:
			return error_reply("Malformed profile")

		if MEMCACHED_ENABLED:
			mc.set("profile_" + str(key),json.dumps(info),int(time() + MEMCACHED_TIMEOUT))
			#print "cache miss full_profile"
	else:
		#print "cache hit full_profile"
		info = json.loads(cache_reply)

	if 'status' in info:
		if info['status'] == 404:
			abort(404)
			
	return jsonify(info)

#-----------------------------------
@app.route('/resolver/bulk')
@requires_auth
def get_bulk_profiles():
	
	usernames = request.args.get('usernames')

	if usernames is None:
		return jsonify(error_reply("No usernames given"))
	
	usernames = usernames.rsplit(',')

	list = [] 

	for username in usernames:

		result = {}
		result["username"] = username 
		result["profile"] = full_profile_mem('u/' + username.lower())

		list.append(result)
			
	return jsonify(results=list)

#-----------------------------------
@app.route('/resolver/namespace')
@requires_auth
def get_namespace():

	from commontools import get_json
	
	users = namecoind.name_filter('u/')

	list = [] 

	for user in users:
		try: 
			username = user['name'].lstrip('u/').lower()
			profile = get_json(user['value'])

			if 'status' in profile and profile['status'] == -1:
				continue

			if 'status' in profile and profile['status'] == 'reserved':
				continue 

			if profile == {}:
				continue

			if 'next' in profile:
				profile = full_profile_mem('u/' + username)

			result = {}
			result["username"] = username  
			result["profile"] = profile 
			list.append(result)

		except Exception as e:
			continue

	return jsonify(results=list)

#-----------------------------------
@app.route('/')
def index():
	return '<hmtl><body>Welcome to openname-resolver, see <a href="http://github.com/opennamesystem"github page</a> for details.</body></html>'

#-----------------------------------
@app.errorhandler(500)
def internal_error(error):

	reply = []
	return json.dumps(reply)

#-----------------------------------
@app.errorhandler(404)
def not_found(error):
	return make_response(jsonify( { 'error': 'Not found' } ), 404)
