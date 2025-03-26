#include <stdio.h>

extern struct rtpkt {
  int sourceid;       /* id of sending router sending this pkt */
  int destid;         /* id of router to which pkt being sent 
                         (must be an immediate neighbor) */
  int mincost[4];    /* min cost to node 0 ... 3 */
  };

extern int TRACE;
extern int YES;
extern int NO;
extern float clocktime;
int connectcosts3[4] = { 7,  999,  2, 0 };

struct distance_table 
{
  int costs[4][4];
} dt3;

/* students to write the following two routines, and maybe some others */

void rtinit3() 
{
    for(int i=0; i< 4; i++){
        for(int j=0; j<4; j++){
            dt3.costs[i][j] = 999;
        }
    }
    for(int i=0; i<4; i++){
        dt3.costs[i][i] = connectcosts3[i];
    }  

    dt3.costs[3][0] = dt3.costs[0][3] =  7;
    dt3.costs[3][1] = dt3.costs[1][3] = 999;
    dt3.costs[3][2] = dt3.costs[2][3] = 2;
    
    struct rtpkt p3;
    p3.sourceid = 3;
    p3.mincost[0] = dt3.costs[3][0];
    p3.mincost[1] = dt3.costs[3][1];
    p3.mincost[2] = dt3.costs[3][2];
    p3.mincost[3] = dt3.costs[3][3];

    p3.destid = 0;
    tolayer2(p3);
    p3.destid = 2;
    tolayer2(p3);
    printf("init 3 clocktime = %f\n", clocktime);
    printf("init distance table of node 3 :\n");
    printdt3(&dt3);
}


void rtupdate3(struct rtpkt *rcvdpkt)
{
    int source = rcvdpkt->sourceid;
    if (source < 0 || source >= 4)
        return;

    int changed = 0;

    for (int dest = 0; dest < 4; dest++) {
        int newcost = connectcosts3[source] + rcvdpkt->mincost[dest];
        if (newcost > 999) newcost = 999;
        dt3.costs[source][dest] = newcost;
    }

    for (int dest = 0; dest < 4; dest++) {
        int oldcost = dt3.costs[3][dest];
        int best = 999;

        for (int via = 0; via < 4; via++) {
            if (dt3.costs[via][dest] < best) {
                best = dt3.costs[via][dest];
            }
        }

        if (best < oldcost) {
            dt3.costs[3][dest] = best;
            changed = 1;
        }
    }

    if (changed) {
        struct rtpkt packet;
        packet.sourceid = 3;
        for (int dest = 0; dest < 4; dest++) {
            packet.mincost[dest] = dt3.costs[3][dest];
        }

        packet.destid = 0;
        tolayer2(packet);
        packet.destid = 2;
        tolayer2(packet);

        printf("update table 3\n");
        printdt3(&dt3);
    } else {
        printf("No Update in node 3\n");
    }
}



printdt3(dtptr)
  struct distance_table *dtptr;
  
{
  printf("             via     \n");
  printf("   D3 |    0     2 \n");
  printf("  ----|-----------\n");
  printf("     0|  %3d   %3d\n",dtptr->costs[0][0], dtptr->costs[2][0]);
  printf("dest 1|  %3d   %3d\n",dtptr->costs[0][1], dtptr->costs[2][1]);
  printf("     2|  %3d   %3d\n",dtptr->costs[0][2], dtptr->costs[2][2]);

}






