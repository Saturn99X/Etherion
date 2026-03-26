"""
DNS Manager Service for Subdomain Validation and Management.

Handles subdomain validation, reserved subdomain checking, and subdomain extraction
from request headers for tenant routing.
"""

import os
from typing import Optional, Set
import re
from fastapi import Request

_PRIMARY_DOMAIN = os.environ.get("PRIMARY_DOMAIN", "localhost")

# Banned words (1,662 total) - embedded directly for deployment reliability
BANNED_WORDS: Set[str] = {'assklown', 'shitcan', 'tonguein', 'shitter', 'muffdiving', 'sixtyniner', 'koon', 'balls', 'cunntt', 'zipper', 'cameltoe', 'heroin', 'urethra-play', 'nutfucker', 'mulatto', 'butthole', 'suicide-girls', 'sultry-women', 'dipstick', 'mams', 'taint', 'kaffir', 'kike', 'butt', 'homobangers', 'lesbain', 'bastard', 'voyuer', 'lickers', 'skumbag', 'orgies', 'roundeye', 'terrorist', 'cunilingus', 'fister', 'pisser', 'analsex', 'upthebutt', 'tongue-in-a', 'wn', 'asswipe', 'skin', 'cuntlicking', 'cumfest', 'premature', 'scumbag', 'sexual', 'cunillingus', 'sodom', 'lezbo', 'eatme', 'cocksmoker', 'skankbitch', 'footstar', 'brea5t', 'bloody', 'felching', 'geez', 'footlicker', 'assjockey', 'shithouse', 'kum', 'butchbabes', 'crotchmonkey', 'buttfuck', 'cockhead', 'asspirate', 'cocknob', 'genitals', 'fetish', 'kyke', 'beatyourmeat', 'gob', 'urinate', 'lezbe', 'suicide', 'deth', 'fondle', 'urine', 'ballsack', 'nudity', 'assranger', 'spitter', 'commie', 'fistfucked', 'lovebone', 'butchdyke', 'mick', 'clogwog', 'ballzitch', 'eatballs', 'pu55i', 'jerk-off', 'snot', 'jiggy', 'pom', 'dix', 'footjob', 'shag', 'snigger', 'zipperhead', 'titfucker', 'blowjob', 'sucks', 'ball-kicking', 'cumshot', 'darky', 'missionary-position', 'fingerfucking', 'cuntsucker', 'sexwhore', 'bimbo', 'lezbe', 'motherlovebone', 'faeces', 'cigs', 'kumbullbe', 'dope', 'rump', 'poof', 'gaymuthafucking', 'pearlnecklace', 'anus', 'buttfuck', 'foreskin', 'wetback', 'titbitnipply', 'mothafucka', 'fuckknob', 'asshole', 'cockrider', 'osama', 'tub-girl', 'usama', 'lesbian', 'flatulence', 'cocksucking', 'asslick', 'cocky', 'peepshpw', 'sandnigger', 'cigs', 'ball-licking', 'fatso', 'jelly-donut', 'pric', 'church', 'cumming', 'bigbastard', 'barf', 'sexymoma', 'pedophile', 'bi', 'booby', 'doggy-style', 'peni5', 'cocksuck', 'honkers', 'willy', 'asian', 'nig-nog', 'weenie', 'pedobear', 'bootycall', 'raghead', 'sandm', 'cockcowboy', 'doggystyle', 'kummer', 'white-power', 'booty', 'shitfaced', 'hoser', 'prickhead', 'motherfucking', 'fuuck', 'wank', 'sexual', 'tnt', 'pendy', 'whore', 'shitforbrains', 'cum', 'cocklover', 'shitty', 'fuckwhore', 'lesbo', 'gypo', 'hamas', 'mattressprincess', 'coprolagnia', 'pedophile', 'fuckfest', 'buttmunch', 'pisshead', 'paedophile', 'jewish', 'chinky', 'splittail', 'sexo', 'nudity', 'transexual', 'nudist', 'crapper', 'bogan', 'spunk', 'fuckfreak', 'shithappens', 'goy', 'poon', 'fingerfucker', 'fuckme', 'skankwhore', 'mong', 'cocksmith', 'threesome', 'shemale', 'testicle', 'bestial', 'homoerotic', 'cocksman', 'mufflikcer', 'suck', 'urinary', 'cocksucked', 'erotic', 'pubes', 'footaction', 'lubejob', 'erection', 'boy', 'boob', 'russki', 'headfuck', 'pissoff', 'skanky', 'dildo', 'dyke', 'dirty-pillows', 'shiz', 'nastyho', 'cuntt', 'masterbate', 'tramp', 'orgies', 'bisexual', 'kinbaku', 'penises', 'coolie', 'boong', 'bung', 'bumfuck', 'nastyslut', 'footfucker', 'pimpjuice', 'cocksucking', 'screw', 'lezzo', 'skankywhore', 'pussy', 'kinky', 'lovemaking', 'sexual', 'nastywhore', 'beastality', 'fuckhead', 'fuckbuddy', 'tit', 'purinapricness', 'fuckmonkey', 'god', 'orgasm', 'buttnugget', 'fuckmehard', 'orgy', 'pisses', 'sluts', 'tampon', 'cumshots', 'snownigger', 'shitface', 'cock', 'pussypounder', 'lesbin', 'sex', 'doggystyle', 'penile', 'coondog', 'fuckpig', 'titjob', 'ejaculating', 'buttman', 'greaseball', 'slut', 's&m', 'sex', 'balls', 'bollock', 'skeet', 'shota', 'denephew', 'shrimping', 'niggur', 'defecate', 'dyefly', 'ass', 'tits', 'slav', 'asscowboy', 'goddamned', 'hell', 'titlicker', 'nastywhore', 'biatch', 'sex', 'frotting', 'butchbabes', 'boody', 'whiz', 'excrement', 'lez', 'cuntfucker', 'mastrabator', 'gummer', 'sextoys', 'bitch', 'smut', 'fuckbag', 'bitchin', 'sexfarm', 'buttplug', 'camwhore', 'pussies', 'cocksuck', 'bestiality', 'niggas', 'butt-bang', 'kumbubble', 'nastywhore', 'tittie', 'snatchpatch', 'dildo', 'nutten', 'sexkitten', 'bitchslap', 'boonie', 'menage-a-trois', 'smackthemonkey', 'buttnugget', 'manhater', 'crabs', 'slanteye', 'pissed', 'niggaz', 'crackpipe', 'doggie-style', 'spankthemonkey', 'bung', 'niggle', 'honkey', 'beaver', 'shitfit', 'niggerhole', 'chink', 'sexcam', 'cocksuck', 'cuntlicking', 'boang', 'nutfuck', 'fellatio', 'peepshow', 'beaver-cleaver', 'sniggering', 'bumfuck', 'nudger', 'rape', 'beaver-lips', 'big-knockers', 'sniggered', 'buttnugget', 'nymphomania', 'bang', 'booger', 'sextoy', 'vaginal', 'pussies', 'bitch', 'hooters', 'penis', 'bomb', 'neocons', 'cockcowboy', 'masturbate', 'cocksuck', 'niggardliness', 'sodomize', 'kinbaku', 'cumming', 'suicide', '2-girls-1-cup', 'alabama-hot-pocket', 'alaskan-pipeline', 'anilingus', 'anus', 'ass', 'asshole', 'assmunch', 'auto-erotic', 'autoerotic', 'babeland', 'baby-batter', 'baby-juice', 'ball-gag', 'ball-gravy', 'ball-kicking', 'ball-licking', 'ball-sack', 'ball-sucking', 'bangbros', 'bangbus', 'bareback', 'barely-legal', 'barenaked', 'bastard', 'bastardo', 'bastinado', 'bbw', 'bdsm', 'beaner', 'beaners', 'beaver-cleaver', 'beaver-lips', 'beastiality', 'bestiality', 'big-black', 'big-breasts', 'big-knockers', 'big-tits', 'bimbos', 'birdlock', 'bitch', 'bitches', 'black-cock', 'blonde-action', 'blonde-on-blonde-action', 'blowjob', 'blow-job', 'blow-your-load', 'blue-waffle', 'blumpkin', 'bollocks', 'bondage', 'boner', 'boob', 'boobs', 'booty-call', 'brown-showers', 'brunette-action', 'bukkake', 'bulldyke', 'bullet-vibe', 'bullshit', 'bung-hole', 'bunghole', 'busty', 'butt', 'buttcheeks', 'butthole', 'camel-toe', 'camgirl', 'camslut', 'camwhore', 'carpet-muncher', 'carpetmuncher', 'chocolate-rosebuds', 'cialis', 'circlejerk', 'cleveland-steamer', 'clit', 'clitoris', 'clover-clamps', 'clusterfuck', 'cock', 'cocks', 'coprolagnia', 'coprophilia', 'cornhole', 'coon', 'coons', 'creampie', 'cum', 'cumming', 'cumshot', 'cumshots', 'cunnilingus', 'cunt', 'darkie', 'date-rape', 'daterape', 'deep-throat', 'deepthroat', 'dendrophilia', 'dick', 'dildo', 'dingleberry', 'dingleberries', 'dirty-pillows', 'dirty-sanchez', 'doggie-style', 'doggiestyle', 'doggy-style', 'doggystyle', 'dog-style', 'dolcett', 'domination', 'dominatrix', 'dommes', 'donkey-punch', 'double-dong', 'double-penetration', 'dp-action', 'dry-hump', 'dvda', 'eat-my-ass', 'ecchi', 'ejaculation', 'erotic', 'erotism', 'escort', 'eunuch', 'fag', 'faggot', 'fecal', 'felch', 'fellatio', 'feltch', 'female-squirting', 'femdom', 'figging', 'fingerbang', 'fingering', 'fisting', 'foot-fetish', 'footjob', 'frotting', 'fuck', 'fuck-buttons', 'fuckin', 'fucking', 'fucktards', 'fudge-packer', 'fudgepacker', 'futanari', 'gangbang', 'gang-bang', 'gay-sex', 'genitals', 'giant-cock', 'girl-on', 'girl-on-top', 'girls-gone-wild', 'goatcx', 'goatse', 'god-damn', 'gokkun', 'golden-shower', 'goodpoop', 'goo-girl', 'goregasm', 'grope', 'group-sex', 'g-spot', 'guro', 'hand-job', 'handjob', 'hard-core', 'hardcore', 'hentai', 'homoerotic', 'honkey', 'hooker', 'horny', 'hot-carl', 'hot-chick', 'how-to-kill', 'how-to-murder', 'huge-fat', 'humping', 'incest', 'intercourse', 'jack-off', 'jail-bait', 'jailbait', 'jelly-donut', 'jerk-off', 'jigaboo', 'jiggaboo', 'jiggerboo', 'jizz', 'juggs', 'kike', 'kinbaku', 'kinkster', 'kinky', 'knobbing', 'leather-restraint', 'leather-straight-jacket', 'lemon-party', 'livesex', 'lolita', 'lovemaking', 'make-me-come', 'male-squirting', 'masturbate', 'masturbating', 'masturbation', 'menage-a-trois', 'milf', 'missionary-position', 'mong', 'motherfucker', 'mound-of-venus', 'mr-hands', 'muff-diver', 'muffdiving', 'nambla', 'nawashi', 'negro', 'neonazi', 'nigga', 'nigger', 'nig-nog', 'nimphomania', 'nipple', 'nipples', 'nsfw', 'nsfw-images', 'nude', 'nudity', 'nutten', 'nympho', 'nymphomania', 'octopussy', 'omorashi', 'one-cup-two-girls', 'one-guy-one-jar', 'orgasm', 'orgy', 'paedophile', 'paki', 'panties', 'panty', 'pedobear', 'pedophile', 'pegging', 'penis', 'phone-sex', 'piece-of-shit', 'pikey', 'pissing', 'piss-pig', 'pisspig', 'playboy', 'pleasure-chest', 'pole-smoker', 'ponyplay', 'poof', 'poon', 'poontang', 'punany', 'poop-chute', 'poopchute', 'porn', 'porno', 'pornography', 'prince-albert-piercing', 'pthc', 'pubes', 'pussy', 'queaf', 'queef', 'quim', 'raghead', 'raging-boner', 'rape', 'raping', 'rapist', 'rectum', 'reverse-cowgirl', 'rimjob', 'rimming', 'rosy-palm', 'rosy-palm-and-her-5-sisters', 'rusty-trombone', 'sadism', 'santorum', 'scat', 'schlong', 'scissoring', 'semen', 'sex', 'sexcam', 'sexo', 'sexy', 'sexual', 'sexually', 'sexuality', 'shaved-beaver', 'shaved-pussy', 'shemale', 'shibari', 'shit', 'shitblimp', 'shitty', 'shota', 'shrimping', 'skeet', 'slanteye', 'slut', 's&m', 'smut', 'snatch', 'snowballing', 'sodomize', 'sodomy', 'spastic', 'spic', 'splooge', 'splooge-moose', 'spooge', 'spread-legs', 'spunk', 'strap-on', 'strapon', 'strappado', 'strip-club', 'style-doggy', 'suck', 'sucks', 'suicide-girls', 'sultry-women', 'swastika', 'swinger', 'tainted-love', 'taste-my', 'tea-bagging', 'threesome', 'throating', 'thumbzilla', 'tied-up', 'tight-white', 'tit', 'tits', 'titties', 'titty', 'tongue-in-a', 'topless', 'tosser', 'towelhead', 'tranny', 'tribadism', 'tub-girl', 'tubgirl', 'tushy', 'twat', 'twink', 'twinkie', 'two-girls-one-cup', 'undressing', 'upskirt', 'urethra-play', 'urophilia', 'vagina', 'venus-mound', 'viagra', 'vibrator', 'violet-wand', 'vorarephilia', 'voyeur', 'voyeurweb', 'voyuer', 'vulva', 'wank', 'wetback', 'wet-dream', 'white-power', 'whore', 'worldsex', 'wrapping-men', 'wrinkled-starfish', 'xx', 'xxx', 'yaoi', 'yellow-showers', 'yiffy', 'zoophilia', 'zoophile', '🖕', 'abbo', 'abo', 'abortion', 'abuse', 'addict', 'addicts', 'adult', 'africa', 'african', 'alla', 'allah', 'alligatorbait', 'amateur', 'american', 'analannie', 'analsex', 'angie', 'angry', 'arab', 'arabs', 'areola', 'argie', 'aroused', 'arse', 'asian', 'assassin', 'assassinate', 'assassination', 'assault', 'assbagger', 'assblaster', 'assclown', 'asscowboy', 'asses', 'assfuck', 'assfucker', 'asshat', 'assholes', 'asshore', 'assjockey', 'asskiss', 'asskisser', 'assklown', 'asslick', 'asslicker', 'asslover', 'assman', 'assmonkey', 'assmuncher', 'asspacker', 'asspirate', 'asspuppies', 'assranger', 'asswhore', 'asswipe', 'athletesfoot', 'attack', 'australian', 'babe', 'babies', 'backdoor', 'backdoorman', 'backseat', 'badfuck', 'balllicker', 'balls', 'banging', 'baptist', 'barelylegal', 'barf', 'barface', 'barfface', 'bast', 'bazongas', 'bazooms', 'beast', 'beastality', 'beastial', 'beatoff', 'beat-off', 'beatyourmeat', 'beaver', 'bestial', 'bi', 'biatch', 'bible', 'bicurious', 'bigass', 'bigger', 'bitcher', 'bitchez', 'bitchin', 'bitching', 'bitchslap', 'bitchy', 'biteme', 'black', 'blackman', 'blackout', 'blacks', 'blind', 'blow', 'boang', 'bogan', 'bohunk', 'bollick', 'bollock', 'bomb', 'bombers', 'bombing', 'bombs', 'bomd', 'bong', 'boobies', 'booby', 'boody', 'boom', 'boong', 'boonga', 'boonie', 'booty', 'bountybar', 'bra', 'breast', 'breastjob', 'breastlover', 'breastman', 'brothel', 'bugger', 'buggered', 'buggery', 'bulldike', 'bumblefuck', 'bunga', 'buried', 'burn', 'butchbabes', 'butchdike', 'butchdyke', 'buttbang', 'butt-bang', 'buttface', 'butt-fucker', 'buttfuckers', 'butt-fuckers', 'butthead', 'buttmunch', 'buttmuncher', 'buttpirate', 'buttplug', 'buttstain', 'byatch', 'cacker', 'cameljockey', 'cameltoe', 'canadian', 'cancer', 'carruth', 'catholic', 'catholics', 'cemetery', 'chav', 'cherrypopper', 'chickslick', "children's", 'chin', 'chinaman', 'chinamen', 'chinese', 'chink', 'chinky', 'choad', 'chode', 'christ', 'christian', 'church', 'cigarette', 'cigs', 'clamdigger', 'clamdiver', 'clogwog', 'cocaine', 'cockblock', 'cockblocker', 'cockcowboy', 'cockfight', 'cockhead', 'cockknob', 'cocklicker', 'cocklover', 'cocknob', 'cockqueen', 'cockrider', 'cocksman', 'cocksmith', 'cocksmoker', 'cocksucer', 'cocksuck', 'cocksucked', 'cocksucker', 'cocktail', 'cocktease', 'cocky', 'cohee', 'coitus', 'color', 'colored', 'colored', 'commie', 'communist', 'condom', 'conservative', 'conspiracy', 'coolie', 'cooly', 'coondog', 'copulate', 'corruption', 'crabs', 'crack', 'crackpipe', 'crackwhore', 'crack-whore', 'crap', 'crapola', 'crapper', 'crappy', 'crash', 'cra5h', 'creamy', 'crime', 'crimes', 'criminal', 'criminals', 'crotch', 'crotchjockey', 'crotchmonkey', 'crotchrot', 'cumbubble', 'cumfest', 'cumjockey', 'cumm', 'cummer', 'cumquat', 'cumqueen', 'cunilingus', 'cunillingus', 'cunn', 'cunntt', 'cunteyed', 'cuntfuck', 'cuntlick', 'cuntlicker', 'cuntsucker', 'cybersex', 'cyberslimer', 'dago', 'dahmer', 'dammit', 'damn', 'damnation', 'damnit', 'darky', 'datnigga', 'dead', 'deapthroat', 'death', 'defecate', 'dego', 'demon', 'deposit', 'desire', 'destroy', 'deth', 'devil', 'devilworshipper', 'dickbrain', 'dickforbrains', 'dickhead', 'dickless', 'dicklick', 'dicklicker', 'dickman', 'dickwad', 'dickweed', 'diddle', 'die', 'died', 'dies', 'dike', 'dink', 'dipshit', 'dipstick', 'dirty', 'disease', 'diseases', 'disturbed', 'dive', 'dix', 'dixiedike', 'dixiedyke', 'dong', 'doodoo', 'doo-doo', 'doom', 'dope', 'dragqueen', 'dragqween', 'dripdick', 'drug', 'drunk', 'drunken', 'dumb', 'dumbass', 'dumbbitch', 'dumbfuck', 'dyefly', 'dyke', 'easyslut', 'eatballs', 'eatme', 'eatpussy', 'ecstacy', 'ejaculate', 'ejaculated', 'ejaculating', 'enema', 'enemy', 'erect', 'erection', 'ero', 'ethiopian', 'ethnic', 'european', 'evl', 'excrement', 'execute', 'executed', 'execution', 'executioner', 'explosion', 'facefucker', 'faeces', 'fagging', 'fagot', 'failed', 'failure', 'fairies', 'fairy', 'faith', 'fannyfucker', 'fart', 'farted', 'farting', 'farty', 'fastfuck', 'fat', 'fatah', 'fatass', 'fatfuck', 'fatfucker', 'fatso', 'fckcum', 'fear', 'feces', 'felatio', 'felcher', 'felching', 'feltcher', 'feltching', 'fight', 'filipina', 'filipino', 'fingerfood', 'fingerfuck', 'fingerfucked', 'fingerfucker', 'fingerfuckers', 'fingerfucking', 'fire', 'firing', 'fister', 'fistfuck', 'fistfucked', 'fistfucker', 'fistfucking', 'flange', 'flasher', 'flatulence', 'floo', 'flydie', 'flydye', 'fok', 'fondle', 'footaction', 'footfuck', 'footfucker', 'footlicker', 'footstar', 'fore', 'foreskin', 'forni', 'fornicate', 'foursome', 'fourtwenty', 'fraud', 'freakfuck', 'freakyfucker', 'freefuck', 'fu', 'fubar', 'fucck', 'fucka', 'fuckable', 'fuckbag', 'fuckbuddy', 'fucked', 'fuckedup', 'fucker', 'fuckers', 'fuckface', 'fuckfest', 'fuckfreak', 'fuckfriend', 'fuckhead', 'fuckher', 'fuckina', 'fuckingbitch', 'fuckinnuts', 'fuckinright', 'fuckit', 'fuckknob', 'fuckme', 'fuckmehard', 'fuckmonkey', 'fuckoff', 'fuckpig', 'fucks', 'fucktard', 'fuckwhore', 'fuckyou', 'fugly', 'fuk', 'fuks', 'funeral', 'funfuck', 'fungus', 'fuuck', 'gangbanged', 'gangbanger', 'gangsta', 'gatorbait', 'gay', 'gaysex', 'geez', 'geezer', 'geni', 'genital', 'german', 'getiton', 'gin', 'ginzo', 'gipp', 'girls', 'givehead', 'glazeddonut', 'gob', 'god', 'godammit', 'goddamit', 'goddammit', 'goddamn', 'goddamned', 'goddamnes', 'goddamnit', 'goddamnmuthafucker', 'goldenshower', 'gonorrehea', 'gonzagas', 'gook', 'gotohell', 'goy', 'goyim', 'greaseball', 'gringo', 'groe', 'gross', 'grostulation', 'gubba', 'gummer', 'gun', 'gyp', 'gypo', 'gypp', 'gyppie', 'gyppo', 'gyppy', 'hamas', 'hapa', 'harder', 'hardon', 'harem', 'headfuck', 'headlights', 'hebe', 'heeb', 'hell', 'henhouse', 'heroin', 'herpes', 'heterosexual', 'hijack', 'hijacker', 'hijacking', 'hillbillies', 'hindoo', 'hiscock', 'hitler', 'hitlerist', 'hiv', 'ho', 'hobo', 'hodgie', 'hoes', 'hole', 'holestuffer', 'homicide', 'homo', 'homobangers', 'homosexual', 'honger', 'honk', 'honkers', 'honky', 'hook', 'hookers', 'hooters', 'hore', 'hork', 'horn', 'horney', 'horniest', 'horseshit', 'hosejob', 'hoser', 'hostage', 'hotdamn', 'hotpussy', 'hottotrot', 'hummer', 'husky', 'hussy', 'hustler', 'hymen', 'hymie', 'iblowu', 'idiot', 'ikey', 'illegal', 'insest', 'interracial', 'intheass', 'inthebuff', 'israel', 'israeli', "israel's", 'italiano', 'itch', 'jackass', 'jackoff', 'jackshit', 'jacktheripper', 'jade', 'jap', 'japanese', 'japcrap', 'jebus', 'jeez', 'jerkoff', 'jesus', 'jesuschrist', 'jew', 'jewish', 'jiga', 'jigg', 'jigga', 'jiggabo', 'jigger', 'jiggy', 'jihad', 'jijjiboo', 'jimfish', 'jism', 'jiz', 'jizim', 'jizjuice', 'jizm', 'jizzim', 'jizzum', 'joint', 'juggalo', 'jugs', 'junglebunny', 'kaffer', 'kaffir', 'kaffre', 'kafir', 'kanake', 'kid', 'kigger', 'kill', 'killed', 'killer', 'killing', 'kills', 'kink', 'kissass', 'kkk', 'knife', 'knockers', 'kock', 'kondum', 'koon', 'kotex', 'krap', 'krappy', 'kraut', 'kum', 'kumbubble', 'kumbullbe', 'kummer', 'kumming', 'kumquat', 'kums', 'kunilingus', 'kunnilingus', 'kunt', 'ky', 'kyke', 'lactate', 'laid', 'lapdance', 'latin', 'lesbain', 'lesbayn', 'lesbin', 'lesbo', 'lez', 'lezbe', 'lezz', 'lezzo', 'liberal', 'libido', 'licker', 'lickme', 'lies', 'limey', 'limpdick', 'limy', 'lingerie', 'liquor', 'loadedgun', 'looser', 'loser', 'lotion', 'lovebone', 'lovegoo', 'lovegun', 'lovejuice', 'lovemuscle', 'lovepistol', 'loverocket', 'lowlife', 'lsd', 'lubejob', 'lucifer', 'luckycammeltoe', 'lugan', 'lynch', 'macaca', 'mad', 'mafia', 'magicwand', 'mams', 'manhater', 'manpaste', 'marijuana', 'mastabate', 'mastabater', 'masterblaster', 'mastrabator', 'mattressprincess', 'meatbeatter', 'meatrack', 'meth', 'mexican', 'mgger', 'mggor', 'mickeyfinn', 'mideast', 'minority', 'mockey', 'mockie', 'mocky', 'mofo', 'moky', 'moles', 'molest', 'molestation', 'molester', 'molestor', 'moneyshot', 'mooncricket', 'mormon', 'moron', 'moslem', 'mosshead', 'mothafuck', 'mothafucka', 'mothafuckaz', 'mothafucked', 'mothafucker', 'mothafuckin', 'mothafucking', 'mothafuckings', 'motherfuck', 'motherfucked', 'motherfuckin', 'motherfuckings', 'motherlovebone', 'muff', 'muffdive', 'muffdiver', 'muffindiver', 'mufflikcer', 'mulatto', 'muncher', 'munt', 'murder', 'murderer', 'muslim', 'naked', 'narcotic', 'nasty', 'nastybitch', 'nastyho', 'nastyslut', 'nazi', 'necro', 'negroes', 'negroid', "negro's", 'nig', 'niger', 'nigerian', 'nigerians', 'nigg', 'niggah', 'niggaracci', 'niggard', 'niggarded', 'niggarding', 'niggardliness', 'niggardly', 'niggards', "niggard's", 'niggaz', 'niggerhead', 'niggerhole', 'niggers', "nigger's", 'niggle', 'niggled', 'niggles', 'niggling', 'nigglings', 'niggor', 'niggur', 'niglet', 'nignog', 'nigr', 'nigra', 'nigre', 'nip', 'nipplering', 'nittit', 'nlgger', 'nlggor', 'nofuckingway', 'nook', 'nookey', 'nookie', 'noonan', 'nooner', 'nudger', 'nuke', 'nutfucker', 'nymph', 'ontherag', 'oral', 'orga', 'orgasim', 'orgies', 'osama', 'palesimian', 'palestinian', 'pansies', 'pansy', 'panti', 'payo', 'pearlnecklace', 'peck', 'pecker', 'peckerwood', 'pee', 'peehole', 'pee-pee', 'peepshow', 'peepshpw', 'pendy', 'penetration', 'peni5', 'penile', 'penises', 'penthouse', 'period', 'perv', 'pi55', 'picaninny', 'piccaninny', 'pickaninny', 'piker', 'piky', 'pimp', 'pimped', 'pimper', 'pimpjuic', 'pimpjuice', 'pimpsimp', 'pindick', 'piss', 'pisser', 'pisses', 'pisshead', 'pissin', 'pissoff', 'pistol', 'pixie', 'pixy', 'playgirl', 'pocha', 'pocho', 'pocketpool', 'pohm', 'polack', 'pom', 'pommie', 'pommy', 'poo', 'poop', 'pooper', 'pooperscooper', 'pooping', 'poorwhitetrash', 'popimp', 'porchmonkey', 'pornflick', 'pornking', 'pornprincess', 'pot', 'poverty', 'premature', 'pric', 'prick', 'prickhead', 'primetime', 'propaganda', 'pros', 'prostitute', 'protestant', 'pu55i', 'pu55y', 'pube', 'pubic', 'pubiclice', 'pud', 'pudboy', 'pudd', 'puddboy', 'puke', 'puntang', 'purinapricness', 'puss', 'pussie', 'pussies', 'pussycat', 'pussyeater', 'pussyfucker', 'pussylicker', 'pussylips', 'pussylover', 'pussypounder', 'pusy', 'quashie', 'queer', 'quickie', 'ra8s', 'rabbi', 'racial', 'racist', 'radical', 'radicals', 'randy', 'raped', 'raper', 'rearend', 'rearentry', 'redlight', 'redneck', 'reefer', 'reestie', 'refugee', 'reject', 'remains', 'rentafuck', 'republican', 'rere', 'retard', 'retarded', 'ribbed', 'rigger', 'roach', 'robber', 'roundeye', 'rump', 'russki', 'russkie', 'sadis', 'sadom', 'samckdaddy', 'sandm', 'sandnigger', 'satan', 'scag', 'scallywag', 'screw', 'screwyou', 'scrotum', 'scum', 'seppo', 'servant', 'sexed', 'sexfarm', 'sexhound', 'sexhouse', 'sexing', 'sexkitten', 'sexpot', 'sexslave', 'sextogo', 'sextoy', 'sextoys', 'sexwhore', 'sexy-slim', 'shag', 'shaggin', 'shagging', 'shat', 'shav', 'shawtypimp', 'sheeney', 'shhit', 'shinola', 'shitcan', 'shitdick', 'shite', 'shiteater', 'shited', 'shitface', 'shitfaced', 'shitfit', 'shitforbrains', 'shitfuck', 'shitfull', 'shithapens', 'shithappens', 'shithead', 'shithouse', 'shiting', 'shitlist', 'shitola', 'shitoutofluck', 'shits', 'shitstain', 'shitted', 'shitter', 'shitting', 'shoot', 'shooting', 'shortfuck', 'showtime', 'sick', 'sissy', 'sixsixsix', 'sixtynine', 'sixtyniner', 'skank', 'skankbitch', 'skankfuck', 'skankwhore', 'skanky', 'skankybitch', 'skankywhore', 'skinflute', 'skum', 'skumbag', 'slant', 'slapper', 'slaughter', 'slav', 'slave', 'slavedriver', 'sleezebag', 'sleezeball', 'slideitin', 'slime', 'slimeball', 'slimebucket', 'slopehead', 'slopey', 'slopy', 'sluts', 'slutt', 'slutting', 'slutty', 'slutwear', 'slutwhore', 'smack', 'snatchpatch', 'snigger', 'sniggered', 'sniggering', 'sniggers', "snigger's", 'sniper', 'snot', 'snowback', 'snownigger', 'sob', 'sodom', 'sodomise', 'sodomite', 'sonofabitch', 'sonofbitch', 'sooty', 'sos', 'soviet', 'spaghettibender', 'spaghettinigger', 'spank', 'sperm', 'spermacide', 'spermbag', 'spermhearder', 'spermherder', 'spick', 'spig', 'spigotty', 'spik', 'spit', 'spitter', 'splittail', 'spreadeagle', 'spunky', 'squaw', 'stagg', 'stiffy', 'stringer', 'stripclub', 'stroke', 'stroking', 'stupid', 'stupidfuck', 'suckdick', 'sucker', 'suckme', 'suckmyass', 'suckmydick', 'suckmytit', 'suckoff', 'suicide', 'swallow', 'swallower', 'swalow', 'sweetness', 'syphilis', 'taboo', 'taff', 'tampon', 'tang', 'tantra', 'tarbaby', 'tard', 'teat', 'terror', 'terrorist', 'teste', 'testicle', 'testicles', 'thicklips', 'thirdeye', 'thirdleg', 'threeway', 'timbernigger', 'tinkle', 'titbitnipply', 'titfuck', 'titfucker', 'titfuckin', 'titjob', 'titlicker', 'titlover', 'tittie', 'tnt', 'toilet', 'tongethruster', 'tongue', 'tonguethrust', 'tonguetramp', 'tortur', 'torture', 'tramp', 'trannie', 'transexual', 'transsexual', 'transvestite', 'triplex', 'trojan', 'trots', 'tuckahoe', 'tunneloflove', 'turd', 'turnon', 'twobitwhore', 'uck', 'uk', 'unfuckable', 'uptheass', 'upthebutt', 'urinary', 'urinate', 'urine', 'usama', 'uterus', 'vaginal', 'vatican', 'vibr', 'vibrater', 'vietcong', 'violence', 'virgin', 'virginbreaker', 'vomit', 'wab', 'wanker', 'wanking', 'waysted', 'weapon', 'weenie', 'weewee', 'welcher', 'welfare', 'wetb', 'wetspot', 'whacker', 'whash', 'whigger', 'whiskey', 'whiskeydick', 'whiskydick', 'whit', 'whitenigger', 'whites', 'whitetrash', 'whitey', 'whiz', 'whop', 'whorefucker', 'whorehouse', 'wigger', 'willie', 'williewanker', 'willy', 'wn', 'wog', 'wop', 'wtf', 'wuss', 'wuzzie', 'xtc', 'yankee', 'yellowman', 'zigabo', 'zipperhead', 'big-black-cock', 'big-black-dick', 'big-black-penis', 'big-black-pussy', 'big-black-tits', 'big-black-vagina', 'big-black-woman', 'child-fucker', 'child-pussy', 'child-whore', 'child', 'hitlerist'}


# Reserved subdomains that cannot be used for tenants
RESERVED_SUBDOMAINS: Set[str] = {
    # Infrastructure subdomains
    "www", "api", "admin", "app", "auth", "mcp",
    "staging", "dev", "test", "prod", "production", "development",
    "demo", "localhost", "mail", "ftp", "smtp", "pop", "imap",
    "webmail", "cpanel", "whm", "cdn", "static", "assets",
    "media", "files", "download", "upload", "docs", "help",
    "support", "status", "blog", "forum", "community",
    
    # Planets of the solar system
    "mercury", "venus", "earth", "mars", "jupiter",
    "saturn", "uranus", "neptune", "pluto",
    
    # Space and science terms
    "quasar", "blackhole", "kerr", "pulsar", "magnetar",
    "magnetars", "neutron", "supernova", "nebula", "galaxy",
    "cosmos", "universe", "asteroid", "comet", "meteor",
    "meteorite", "satellite", "orbit", "lunar", "solar",
    "stellar", "interstellar", "cosmic", "cosmology",
    "astronomy", "astrophysics", "singularity", "horizon",
    "gravity", "relativity", "quantum", "photon", "electron",
    "proton", "neutron", "atom", "molecule", "particle",
    "antimatter", "dark-matter", "dark-energy", "wormhole",
    "spacetime", "redshift", "blueshift", "doppler",
    "spectrum", "wavelength", "radiation", "gamma",
    "xray", "infrared", "ultraviolet", "telescope",
    "observatory", "nasa", "esa", "spacex", "rocket",
    "shuttle", "station", "iss", "hubble", "voyager",
    "pioneer", "cassini", "galileo", "kepler", "apollo",
    "artemis", "orion", "constellation", "zodiac",
    "eclipse", "equinox", "solstice", "aphelion",
    "perihelion", "exoplanet", "habitable", "goldilocks",
}

# Subdomain validation regex: lowercase letters and hyphens only, 3-12 characters
SUBDOMAIN_PATTERN = re.compile(r'^[a-z]([a-z-]{1,10}[a-z])?$')


def contains_banned_word(text: str) -> bool:
    """
    Check if text contains any banned words.
    
    Args:
        text: Text to check
        
    Returns:
        bool: True if contains banned word, False otherwise
    """
    text = text.lower().replace('-', '')
    
    # Check if the subdomain itself is a banned word
    if text in BANNED_WORDS:
        return True
    
    # Check if subdomain contains any banned word as substring
    for banned_word in BANNED_WORDS:
        # Skip very short banned words to avoid false positives
        if len(banned_word) >= 4 and banned_word in text:
            return True
    
    return False


def is_valid_subdomain(subdomain: str) -> bool:
    """
    Validate that a subdomain meets all requirements.
    
    Requirements:
    - 3-12 characters
    - Lowercase letters and hyphens only
    - Cannot start or end with hyphen
    - Cannot contain consecutive hyphens
    - Cannot be a reserved subdomain
    - Cannot contain banned words
    
    Args:
        subdomain: The subdomain to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not subdomain:
        return False
    
    # Convert to lowercase
    subdomain = subdomain.lower().strip()
    
    # Check length (3-12 characters)
    if len(subdomain) < 3 or len(subdomain) > 12:
        return False
    
    # Check format: lowercase letters and hyphens only
    if not SUBDOMAIN_PATTERN.match(subdomain):
        return False
    
    # Check for reserved subdomains
    if subdomain in RESERVED_SUBDOMAINS:
        return False
    
    # Cannot start or end with hyphen
    if subdomain.startswith('-') or subdomain.endswith('-'):
        return False
    
    # Cannot contain consecutive hyphens
    if '--' in subdomain:
        return False
    
    # Check for banned words
    if contains_banned_word(subdomain):
        return False
    
    return True


def normalize_subdomain(subdomain: str) -> str:
    """
    Normalize a subdomain to a valid DNS format.
    
    Args:
        subdomain: The subdomain to normalize
        
    Returns:
        str: Normalized subdomain
    """
    # Convert to lowercase, replace spaces/underscores with hyphens
    normalized = subdomain.lower().strip().replace(' ', '-').replace('_', '-')
    
    # Remove non-alphabetic characters except hyphens
    normalized = re.sub(r'[^a-z-]', '', normalized)
    
    # Remove consecutive hyphens
    normalized = re.sub(r'-+', '-', normalized)
    
    # Remove leading/trailing hyphens
    normalized = normalized.strip('-')
    
    # Truncate to 12 characters
    if len(normalized) > 12:
        normalized = normalized[:12].rstrip('-')
    
    return normalized


def generate_unique_subdomain(base: str, existing_subdomains: Set[str]) -> str:
    """
    Generate a unique subdomain by appending numbers if needed.
    
    Args:
        base: Base subdomain name
        existing_subdomains: Set of existing subdomains to check against
        
    Returns:
        str: Unique subdomain
    """
    base = normalize_subdomain(base)
    
    if not base or len(base) < 3:
        base = "tenant"
    
    # If base is valid and not taken, use it
    if is_valid_subdomain(base) and base not in existing_subdomains:
        return base
    
    # Try appending numbers (keep within 12 char limit)
    max_base_len = 10  # Leave room for 2-digit number
    short_base = base[:max_base_len].rstrip('-')
    
    for i in range(1, 100):
        candidate = f"{short_base}{i}"
        if is_valid_subdomain(candidate) and candidate not in existing_subdomains:
            return candidate
    
    # Fallback: use shorter base + random suffix
    import secrets
    random_suffix = secrets.token_hex(2)[:2]  # 2 hex chars
    fallback = f"{base[:8]}-{random_suffix}"
    return fallback if is_valid_subdomain(fallback) else "tenant-1"


def extract_subdomain_from_host(host: str, primary_domain: str = None) -> Optional[str]:
    if primary_domain is None:
        primary_domain = _PRIMARY_DOMAIN
    """
    Extract subdomain from HTTP Host header.
    
    Args:
        host: HTTP Host header value
        primary_domain: Primary domain name
        
    Returns:
        Optional[str]: Subdomain if found, None otherwise
    """
    if not host:
        return None
    
    # Remove port if present
    host = host.split(':')[0].lower()
    
    # Check if it matches the pattern subdomain.primary_domain
    if not host.endswith('.' + primary_domain):
        return None
    
    # Extract subdomain
    subdomain = host[:-len(primary_domain)-1]
    
    # Validate it's a single subdomain (no nested subdomains)
    if '.' in subdomain:
        return None
    
    return subdomain if subdomain else None


def extract_subdomain_from_request(request: Request, primary_domain: str = None) -> Optional[str]:
    if primary_domain is None:
        primary_domain = _PRIMARY_DOMAIN
    """
    Extract subdomain from FastAPI Request object.
    
    Args:
        request: FastAPI Request object
        primary_domain: Primary domain name
        
    Returns:
        Optional[str]: Subdomain if found, None otherwise
    """
    # Get Host header
    host = request.headers.get("host")
    if not host:
        return None
    
    return extract_subdomain_from_host(host, primary_domain)


class DNSManager:
    """
    DNS Manager for subdomain operations.
   
    Note: With wildcard DNS (e.g. *.yourdomain.com), we don't need to create
    individual DNS records. All subdomains automatically resolve to the
    load balancer IP. Set PRIMARY_DOMAIN env var to your actual domain.
    """
    
    def __init__(self, primary_domain: str = None):
        if primary_domain is None:
            primary_domain = _PRIMARY_DOMAIN
        self.primary_domain = primary_domain
    
    def validate_subdomain(self, subdomain: str) -> tuple[bool, Optional[str]]:
        """
        Validate a subdomain for tenant creation.
        
        Args:
            subdomain: Subdomain to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not subdomain:
            return False, "Subdomain cannot be empty"
        
        # Check for uppercase letters before normalization
        if subdomain != subdomain.lower():
            return False, "Subdomain must be lowercase"
        
        subdomain = subdomain.lower().strip()
        
        if len(subdomain) < 3:
            return False, "Subdomain must be at least 3 characters"
        
        if len(subdomain) > 12:
            return False, "Subdomain must be at most 12 characters"
        
        if not SUBDOMAIN_PATTERN.match(subdomain):
            return False, "Subdomain can only contain lowercase letters and hyphens"
        
        if subdomain in RESERVED_SUBDOMAINS:
            return False, f"'{subdomain}' is a reserved subdomain and cannot be used"
        
        if subdomain.startswith('-') or subdomain.endswith('-'):
            return False, "Subdomain cannot start or end with a hyphen"
        
        if '--' in subdomain:
            return False, "Subdomain cannot contain consecutive hyphens"
        
        if contains_banned_word(subdomain):
            return False, "Subdomain contains prohibited content"
        
        return True, None
    
    def is_subdomain_available(self, subdomain: str) -> bool:
        """
        Check if subdomain is available (not in use).
        
        Args:
            subdomain: Subdomain to check
            
        Returns:
            bool: True if available, False if taken
            
        Note: This should query the database to check if a tenant
        with this subdomain already exists. For now, returns True.
        """
        # TODO: Query database for existing tenant with this subdomain
        # from src.models import Tenant
        # existing = session.query(Tenant).filter_by(subdomain=subdomain).first()
        # return existing is None
        
        return True  # Placeholder
