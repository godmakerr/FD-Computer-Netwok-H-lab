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
int connectcosts2[4] = { 3,  1,  0, 2 };

struct distance_table 
{
  int costs[4][4];
} dt2;


/* students to write the following two routines, and maybe some others */

void rtinit2() 
{
   for(int i=0; i< 4; i++){
        for(int j=0; j<4; j++){
            dt2.costs[i][j] = 999;
        }
    }
    for(int i=0; i<4; i++){
        dt2.costs[i][i] = connectcosts2[i];
    }       

    dt2.costs[2][0] = dt2.costs[0][2] = 3;
    dt2.costs[2][1] = dt2.costs[1][2] = 1;
    dt2.costs[2][3] = dt2.costs[3][2] = 2;
    
    struct rtpkt p2;
    p2.sourceid = 2;
    p2.mincost[0] = dt2.costs[2][0];
    p2.mincost[1] = dt2.costs[2][1];
    p2.mincost[2] = dt2.costs[2][2];
    p2.mincost[3] = dt2.costs[2][3];

    p2.destid = 0;
    tolayer2(p2);
    p2.destid = 1;
    tolayer2(p2);
    p2.destid = 3;
    tolayer2(p2);
    printf("init 2 clocktime = %f\n", clocktime);
    printf("init distance table of node 2 :\n");
    printdt2(&dt2);

}


void rtupdate2(struct rtpkt *rcvdpkt)
{
    int source = rcvdpkt->sourceid;
    if (source < 0 || source >= 4)
        return;

    int changed = 0;

    for (int dest = 0; dest < 4; dest++) {
        int newcost = connectcosts2[source] + rcvdpkt->mincost[dest];
        if (newcost > 999) newcost = 999;
        if(newcost < dt2.costs[source][dest]) 
            changed = 1;
        dt2.costs[source][dest] = newcost;
    }

    for (int dest = 0; dest < 4; dest++) {
        int oldcost = dt2.costs[2][dest]; 
        int best = 999;

        for (int via = 0; via < 4; via++) {
            if (dt2.costs[via][dest] < best) {
                best = dt2.costs[via][dest];
            }
        }

        if (best < oldcost) {
            dt2.costs[2][dest] = best;
            changed = 1;
        }
    }
    
    if (changed) {
        struct rtpkt packet;
        packet.sourceid = 2;
        for (int i = 0; i < 4; ++i)
            packet.mincost[i] = dt2.costs[2][i];
        packet.destid = 0;
        tolayer2(packet);
        packet.destid = 1;
        tolayer2(packet);
        packet.destid = 3;
        tolayer2(packet);
        printf("update table 2\n");
        printdt2(&dt2);
    } else {
        printf("No Update in node 2\n");
    }
}


printdt2(dtptr)
  struct distance_table *dtptr;
  
{
  printf("                via     \n");
  printf("   D2 |    0     1    3 \n");
  printf("  ----|-----------------\n");
  printf("     0|  %3d   %3d   %3d\n",dtptr->costs[0][0],
	 dtptr->costs[1][0],dtptr->costs[3][0]);
  printf("dest 1|  %3d   %3d   %3d\n",dtptr->costs[0][1],
	 dtptr->costs[1][1],dtptr->costs[3][1]);
  printf("     3|  %3d   %3d   %3d\n",dtptr->costs[0][3],
	 dtptr->costs[1][3],dtptr->costs[3][3]);
}


linkhandler2(linkid, newcost)   
  int linkid, newcost;

/* called when cost from 0 to linkid changes from current value to newcost*/
/* You can leave this routine empty if you're an undergrad. If you want */
/* to use this routine, you'll need to change the value of the LINKCHANGE */
/* constant definition in prog3.c from 0 to 1 */
	
{
}