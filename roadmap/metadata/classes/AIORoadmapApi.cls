/**
 * Public roadmap voting endpoint for the AIO Analytics Builder Web UI.
 * Exposed to the AIO Roadmap Site guest user:
 *   GET  /services/apexrest/aio/roadmap?voter={id}        items + vote counts
 *   POST /services/apexrest/aio/roadmap  {action: "picks", voter, itemIds: [1st, 2nd, 3rd]}   set ranked picks
 *   POST /services/apexrest/aio/roadmap  {action: "suggest", voter, title, summary}
 * Each voter ranks up to 3 items: 1st = 3 points, 2nd = 2, 3rd = 1 (Roadmap_Vote__c.Points__c).
 * Voters are anonymous install IDs. Writes are capped per voter per day.
 */
@RestResource(urlMapping='/aio/roadmap/*')
global without sharing class AIORoadmapApi {
    @TestVisible static final Integer MAX_SUGGESTIONS_PER_VOTER_PER_DAY = 3;
    @TestVisible static final Integer MAX_SUGGESTIONS_PER_DAY = 50;
    @TestVisible static final Integer MAX_VOTES_PER_VOTER_PER_DAY = 100;
    @TestVisible static final Integer MAX_PICKS = 3;
    static final Pattern VOTER_ID = Pattern.compile('^[A-Za-z0-9-]{16,64}$');

    @HttpGet
    global static void listItems() {
        String voter = RestContext.request.params.get('voter');
        respond(200, new Map<String, Object>{ 'items' => items(isVoter(voter) ? voter : null) });
    }

    @HttpPost
    global static void post() {
        Map<String, Object> body;
        try {
            body = (Map<String, Object>) JSON.deserializeUntyped(RestContext.request.requestBody.toString());
        } catch (Exception e) {
            respond(400, error('Body must be a JSON object'));
            return;
        }
        String action = (String) body.get('action');
        String voter = (String) body.get('voter');
        if (!isVoter(voter)) {
            respond(400, error('Missing or invalid voter ID'));
            return;
        }
        if (action == 'picks') {
            List<String> ids = new List<String>();
            Object raw = body.get('itemIds');
            if (raw instanceof List<Object>) {
                for (Object o : (List<Object>) raw) ids.add(String.valueOf(o));
            }
            setPicks(voter, ids);
        } else if (action == 'suggest') {
            suggest(voter, (String) body.get('title'), (String) body.get('summary'));
        } else {
            respond(400, error('Unknown action'));
        }
    }

    static void setPicks(String voter, List<String> itemIds) {
        List<Id> ordered = new List<Id>();
        for (String raw : itemIds) {
            Id itemId = safeId(raw);
            if (itemId == null || ordered.contains(itemId)) {
                respond(400, error('Picks must be distinct roadmap item IDs'));
                return;
            }
            ordered.add(itemId);
        }
        if (ordered.size() > MAX_PICKS) {
            respond(400, error('Pick up to ' + MAX_PICKS + ' items'));
            return;
        }
        Integer open = [SELECT COUNT() FROM Roadmap_Item__c WHERE Id IN :ordered AND Status__c NOT IN ('Completed', 'Declined')];
        if (open != ordered.size()) {
            respond(404, error('Roadmap item not found'));
            return;
        }
        Integer today = [SELECT COUNT() FROM Roadmap_Vote__c WHERE Voter_Id__c = :voter AND LastModifiedDate = TODAY];
        if (today >= MAX_VOTES_PER_VOTER_PER_DAY) {
            respond(429, error('Vote limit reached for today'));
            return;
        }
        Map<Id, Roadmap_Vote__c> mine = new Map<Id, Roadmap_Vote__c>();
        for (Roadmap_Vote__c v : [SELECT Id, Item__c, Active__c, Pick_Rank__c FROM Roadmap_Vote__c WHERE Voter_Id__c = :voter]) {
            mine.put(v.Item__c, v);
        }
        List<Roadmap_Vote__c> changes = new List<Roadmap_Vote__c>();
        for (Integer i = 0; i < ordered.size(); i++) {
            Roadmap_Vote__c v = mine.remove(ordered[i]);
            if (v == null) {
                changes.add(new Roadmap_Vote__c(Item__c = ordered[i], Voter_Id__c = voter,
                                                Vote_Key__c = ordered[i] + ':' + voter, Active__c = true, Pick_Rank__c = i + 1));
            } else if (!v.Active__c || v.Pick_Rank__c != i + 1) {
                v.Active__c = true;
                v.Pick_Rank__c = i + 1;
                changes.add(v);
            }
        }
        for (Roadmap_Vote__c v : mine.values()) {
            if (v.Active__c) {
                v.Active__c = false;
                changes.add(v);
            }
        }
        upsert changes;
        respond(200, new Map<String, Object>{ 'items' => items(voter) });
    }

    static void suggest(String voter, String title, String summary) {
        title = title == null ? '' : title.normalizeSpace();
        summary = summary == null ? '' : summary.normalizeSpace();
        if (title.length() < 4 || title.length() > 80) {
            respond(400, error('Title must be 4-80 characters'));
            return;
        }
        if (summary.length() > 255) {
            respond(400, error('Summary must be 255 characters or fewer'));
            return;
        }
        Integer mine = [SELECT COUNT() FROM Roadmap_Item__c WHERE Suggested_By__c = :voter AND CreatedDate = TODAY];
        Integer everyone = [SELECT COUNT() FROM Roadmap_Item__c WHERE Source__c = 'SE suggestion' AND CreatedDate = TODAY];
        if (mine >= MAX_SUGGESTIONS_PER_VOTER_PER_DAY || everyone >= MAX_SUGGESTIONS_PER_DAY) {
            respond(429, error('Suggestion limit reached for today'));
            return;
        }
        Roadmap_Item__c item = new Roadmap_Item__c(
            Name = title, Summary__c = summary, Status__c = 'Suggested', Source__c = 'SE suggestion',
            Suggested_By__c = voter, Item_Key__c = 'se-' + EncodingUtil.convertToHex(Crypto.generateAesKey(128)).left(16)
        );
        insert item;
        // The idea becomes the suggester's next pick if they have a free slot
        Integer picks = [SELECT COUNT() FROM Roadmap_Vote__c WHERE Voter_Id__c = :voter AND Active__c = true];
        if (picks < MAX_PICKS) {
            insert new Roadmap_Vote__c(Item__c = item.Id, Voter_Id__c = voter, Vote_Key__c = item.Id + ':' + voter,
                                       Active__c = true, Pick_Rank__c = picks + 1);
        }
        respond(201, new Map<String, Object>{ 'item' => items(voter, item.Id)[0] });
    }

    static List<Map<String, Object>> items(String voter) {
        return items(voter, null);
    }

    static List<Map<String, Object>> items(String voter, Id onlyId) {
        List<Roadmap_Item__c> rows = onlyId != null
            ? [SELECT Id, Name, Item_Key__c, Summary__c, Status__c, Source__c, Priority_Rank__c, Vote_Count__c, Points__c, CreatedDate
               FROM Roadmap_Item__c WHERE Id = :onlyId]
            : [SELECT Id, Name, Item_Key__c, Summary__c, Status__c, Source__c, Priority_Rank__c, Vote_Count__c, Points__c, CreatedDate
               FROM Roadmap_Item__c
               WHERE Status__c NOT IN ('Completed', 'Declined')
               ORDER BY Priority_Rank__c ASC NULLS LAST, Points__c DESC, Vote_Count__c DESC, CreatedDate DESC
               LIMIT 200];
        Map<Id, Integer> myRank = new Map<Id, Integer>();
        if (voter != null) {
            for (Roadmap_Vote__c v : [SELECT Item__c, Pick_Rank__c FROM Roadmap_Vote__c
                                      WHERE Voter_Id__c = :voter AND Active__c = true AND Pick_Rank__c != null]) {
                myRank.put(v.Item__c, v.Pick_Rank__c.intValue());
            }
        }
        List<Map<String, Object>> out = new List<Map<String, Object>>();
        for (Roadmap_Item__c r : rows) {
            out.add(new Map<String, Object>{
                'id' => r.Id, 'key' => r.Item_Key__c, 'title' => r.Name, 'summary' => r.Summary__c,
                'status' => r.Status__c, 'source' => r.Source__c, 'rank' => r.Priority_Rank__c,
                'votes' => r.Vote_Count__c == null ? 0 : r.Vote_Count__c.intValue(),
                'points' => r.Points__c == null ? 0 : r.Points__c.intValue(),
                'myRank' => myRank.get(r.Id), 'created' => r.CreatedDate
            });
        }
        return out;
    }

    static Boolean isVoter(String voter) {
        return voter != null && VOTER_ID.matcher(voter).matches();
    }

    static Id safeId(String value) {
        try {
            return (Id) value;
        } catch (Exception e) {
            return null;
        }
    }

    static Map<String, Object> error(String message) {
        return new Map<String, Object>{ 'error' => message };
    }

    static void respond(Integer status, Object body) {
        RestContext.response.statusCode = status;
        RestContext.response.addHeader('Content-Type', 'application/json');
        RestContext.response.responseBody = Blob.valueOf(JSON.serialize(body));
    }
}
