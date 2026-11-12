@IsTest
private class AIORoadmapApiTest {
    static final String VOTER = 'test-voter-0000000001';

    static Map<String, Object> call(String method, String voterParam, Map<String, Object> body) {
        RestRequest req = new RestRequest();
        req.requestURI = '/services/apexrest/aio/roadmap';
        req.httpMethod = method;
        if (voterParam != null) req.params.put('voter', voterParam);
        if (body != null) req.requestBody = Blob.valueOf(JSON.serialize(body));
        RestContext.request = req;
        RestContext.response = new RestResponse();
        if (method == 'GET') AIORoadmapApi.listItems(); else AIORoadmapApi.post();
        Map<String, Object> out = (Map<String, Object>) JSON.deserializeUntyped(RestContext.response.responseBody.toString());
        out.put('_status', RestContext.response.statusCode);
        return out;
    }

    static Map<String, Object> picks(String voter, List<Id> ids) {
        return call('POST', null, new Map<String, Object>{ 'action' => 'picks', 'voter' => voter, 'itemIds' => ids });
    }

    static Map<String, Map<String, Object>> byTitle(Map<String, Object> out) {
        Map<String, Map<String, Object>> m = new Map<String, Map<String, Object>>();
        for (Object o : (List<Object>) out.get('items')) {
            Map<String, Object> item = (Map<String, Object>) o;
            m.put((String) item.get('title'), item);
        }
        return m;
    }

    @TestSetup
    static void setup() {
        insert new List<Roadmap_Item__c>{
            new Roadmap_Item__c(Name = 'Item A', Item_Key__c = 'item-a', Status__c = 'Next', Source__c = 'Roadmap', Priority_Rank__c = 1),
            new Roadmap_Item__c(Name = 'Item B', Item_Key__c = 'item-b', Status__c = 'Planned', Source__c = 'Roadmap', Priority_Rank__c = 2),
            new Roadmap_Item__c(Name = 'Item C', Item_Key__c = 'item-c', Status__c = 'Planned', Source__c = 'Roadmap', Priority_Rank__c = 3),
            new Roadmap_Item__c(Name = 'Item D', Item_Key__c = 'item-d', Status__c = 'Suggested', Source__c = 'SE suggestion'),
            new Roadmap_Item__c(Name = 'Done item', Item_Key__c = 'done-item', Status__c = 'Completed', Source__c = 'Roadmap')
        };
    }

    static Map<String, Id> ids() {
        Map<String, Id> m = new Map<String, Id>();
        for (Roadmap_Item__c r : [SELECT Id, Item_Key__c FROM Roadmap_Item__c]) m.put(r.Item_Key__c, r.Id);
        return m;
    }

    @IsTest
    static void listsOpenItems() {
        List<Object> items = (List<Object>) call('GET', VOTER, null).get('items');
        System.assertEquals(4, items.size());
        System.assertEquals('Item A', ((Map<String, Object>) items[0]).get('title'));
    }

    @IsTest
    static void rankedPicksScorePoints() {
        Map<String, Id> m = ids();
        Map<String, Map<String, Object>> out = byTitle(picks(VOTER, new List<Id>{ m.get('item-c'), m.get('item-a'), m.get('item-b') }));
        System.assertEquals(3, out.get('Item C').get('points'));
        System.assertEquals(1, out.get('Item C').get('myRank'));
        System.assertEquals(2, out.get('Item A').get('points'));
        System.assertEquals(1, out.get('Item B').get('points'));

        // A second voter's first choice adds up
        out = byTitle(picks('test-voter-0000000002', new List<Id>{ m.get('item-a') }));
        System.assertEquals(5, out.get('Item A').get('points'));
        System.assertEquals(2, out.get('Item A').get('votes'));
        System.assertEquals(null, out.get('Item A').get('myRank'));

        // Reorder + drop: B moves to first, C removed
        out = byTitle(picks(VOTER, new List<Id>{ m.get('item-b'), m.get('item-a') }));
        System.assertEquals(3, out.get('Item B').get('points'));
        System.assertEquals(0, out.get('Item C').get('points'));
        System.assertEquals(null, out.get('Item C').get('myRank'));
        System.assertEquals(5, out.get('Item A').get('points'));

        // Clearing all picks
        out = byTitle(picks(VOTER, new List<Id>()));
        System.assertEquals(0, out.get('Item B').get('points'));
    }

    @IsTest
    static void rejectsBadInput() {
        Map<String, Id> m = ids();
        System.assertEquals(400, picks('short', new List<Id>()).get('_status'));
        System.assertEquals(400, picks(VOTER, new List<Id>{ m.get('item-a'), m.get('item-b'), m.get('item-c'), m.get('item-d') }).get('_status'));
        System.assertEquals(400, picks(VOTER, new List<Id>{ m.get('item-a'), m.get('item-a') }).get('_status'));
        System.assertEquals(404, picks(VOTER, new List<Id>{ m.get('done-item') }).get('_status'));
        System.assertEquals(400, call('POST', null, new Map<String, Object>{ 'action' => 'picks', 'voter' => VOTER,
            'itemIds' => new List<String>{ 'nope' } }).get('_status'));
        System.assertEquals(400, call('POST', null, new Map<String, Object>{ 'action' => 'other', 'voter' => VOTER }).get('_status'));
        System.assertEquals(400, call('POST', null, new Map<String, Object>{ 'action' => 'suggest', 'voter' => VOTER, 'title' => 'x' }).get('_status'));
        System.assertEquals(400, call('POST', null, new Map<String, Object>{ 'action' => 'suggest', 'voter' => VOTER,
            'title' => 'Long summary', 'summary' => 'x'.repeat(256) }).get('_status'));

        RestRequest req = new RestRequest();
        req.httpMethod = 'POST';
        req.requestBody = Blob.valueOf('not json');
        RestContext.request = req;
        RestContext.response = new RestResponse();
        AIORoadmapApi.post();
        System.assertEquals(400, RestContext.response.statusCode);
    }

    @IsTest
    static void suggestionTakesFreePickAndIsCapped() {
        Map<String, Id> m = ids();
        picks(VOTER, new List<Id>{ m.get('item-a'), m.get('item-b') });
        Map<String, Object> out = call('POST', null, new Map<String, Object>{ 'action' => 'suggest', 'voter' => VOTER,
            'title' => 'Data Apps for CRMA', 'summary' => 'Build data apps on CRMA demos' });
        System.assertEquals(201, out.get('_status'));
        Map<String, Object> item = (Map<String, Object>) out.get('item');
        System.assertEquals('Suggested', item.get('status'));
        System.assertEquals(3, item.get('myRank'));
        System.assertEquals(1, item.get('points'));

        // No free pick left: the next idea gets no pick
        out = call('POST', null, new Map<String, Object>{ 'action' => 'suggest', 'voter' => VOTER, 'title' => 'Another idea' });
        System.assertEquals(null, ((Map<String, Object>) out.get('item')).get('myRank'));
        call('POST', null, new Map<String, Object>{ 'action' => 'suggest', 'voter' => VOTER, 'title' => 'Third idea' });
        System.assertEquals(429, call('POST', null, new Map<String, Object>{ 'action' => 'suggest', 'voter' => VOTER,
            'title' => 'One too many' }).get('_status'));
    }
}
