/* Discover only the Sony MDR V1 service; no pairing or settings changes. */
#include <stdio.h>
#include <stdint.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/sdp.h>
#include <bluetooth/sdp_lib.h>

int main(int argc, char **argv) {
    bdaddr_t remote;
    if (argc != 2 || str2ba(argv[1], &remote)) return 2;
    uint8_t bytes[] = {0x96,0xcc,0x20,0x3e,0x50,0x68,0x46,0xad,
                       0xb3,0x2d,0xe3,0x16,0xf5,0xe0,0x69,0xba};
    uuid_t uuid;
    sdp_uuid128_create(&uuid, bytes);
    sdp_session_t *session = sdp_connect(BDADDR_ANY, &remote, SDP_RETRY_IF_BUSY);
    if (!session) { perror("sdp_connect"); return 1; }
    uint32_t range = 0x0000ffff;
    sdp_list_t *search = sdp_list_append(NULL, &uuid);
    sdp_list_t *attrs = sdp_list_append(NULL, &range), *records = NULL;
    int channel = -1;
    if (sdp_service_search_attr_req(session, search, SDP_ATTR_REQ_RANGE, attrs, &records) == 0) {
        for (sdp_list_t *r = records; r; r = r->next) {
            sdp_list_t *protos = NULL;
            if (sdp_get_access_protos(r->data, &protos) == 0) {
                int candidate = sdp_get_proto_port(protos, RFCOMM_UUID);
                if (candidate > 0 && candidate <= 30) channel = candidate;
                for (sdp_list_t *p = protos; p; p = p->next) sdp_list_free(p->data, NULL);
                sdp_list_free(protos, NULL);
            }
            sdp_record_free(r->data);
        }
    }
    sdp_list_free(records, NULL);
    sdp_list_free(search, NULL);
    sdp_list_free(attrs, NULL);
    sdp_close(session);
    if (channel < 1) { fprintf(stderr, "MDR V1 RFCOMM service not found\n"); return 1; }
    printf("%d\n", channel);
    return 0;
}
