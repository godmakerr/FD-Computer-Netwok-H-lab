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
int connectcosts1[4] = { 1,  0,  1, 999 };

struct distance_table 
{
  int costs[4][4];
} dt1;


/* students to write the following two routines, and maybe some others */


rtinit1() 
{
 for(int i=0; i< 4; i++){
        for(int j=0; j<4; j++){
            dt1.costs[i][j] = 999;
        }
    }
    for(int i=0; i<4; i++){
        dt1.costs[i][i] = connectcosts1[i];
    }


    dt1.costs[1][0] = dt1.costs[0][1] = 1;
    dt1.costs[1][2] = dt1.costs[2][1] = 1;
    dt1.costs[1][3] = dt1.costs[3][1] = 999;
    
    struct rtpkt p1;
    p1.sourceid = 1;
    p1.mincost[0] = dt1.costs[1][0];
    p1.mincost[1] = dt1.costs[1][1];
    p1.mincost[2] = dt1.costs[1][2];
    p1.mincost[3] = dt1.costs[1][3];

    p1.destid = 0;
    tolayer2(p1);
    p1.destid = 2;
    tolayer2(p1);
    printf("init 1 clocktime = %f\n", clocktime);
    printf("init distance table of node 1 :\n");
    printdt1(&dt1);

}


void rtupdate1(struct rtpkt *rcvdpkt)
{
    int source = rcvdpkt->sourceid;
    if (source < 0 || source >= 4)
        return;

    int changed = 0;

    for (int dest = 0; dest < 4; dest++) {
        int newcost = connectcosts1[source] + rcvdpkt->mincost[dest];
        if (newcost > 999) newcost = 999;
        dt1.costs[source][dest] = newcost;
    }

    for (int dest = 0; dest < 4; dest++) {
        int oldcost = dt1.costs[1][dest]; 
        int best = 999;

        for (int via = 0; via < 4; via++) {
            if (dt1.costs[via][dest] < best) {
                best = dt1.costs[via][dest];
            }
        }

        if (best < oldcost) {
            dt1.costs[1][dest] = best;
            changed = 1;
        }
    }

    if (changed) {
        struct rtpkt packet;
        packet.sourceid = 1;
        for (int dest = 0; dest < 4; dest++) {
            packet.mincost[dest] = dt1.costs[1][dest];
        }

        packet.destid = 0;
        tolayer2(packet);
        packet.destid = 2;
        tolayer2(packet);

        printf("update table 1\n");
        printdt1(&dt1);
    } else {
        printf("No Update in node 1\n");
    }
}



printdt1(dtptr)
  struct distance_table *dtptr;
  
{
  printf("             via   \n");
  printf("   D1 |    0     2 \n");
  printf("  ----|-----------\n");
  printf("     0|  %3d   %3d\n",dtptr->costs[0][0], dtptr->costs[2][0]);
  printf("dest 2|  %3d   %3d\n",dtptr->costs[0][2], dtptr->costs[2][2]);
  printf("     3|  %3d   %3d\n",dtptr->costs[0][3], dtptr->costs[2][3]);

}



linkhandler1(linkid, newcost)   
int linkid, newcost;   
/* called when cost from 1 to linkid changes from current value to newcost*/
/* You can leave this routine empty if you're an undergrad. If you want */
/* to use this routine, you'll need to change the value of the LINKCHANGE */
/* constant definition in prog3.c from 0 to 1 */
	
{
}

